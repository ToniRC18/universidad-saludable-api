import io
import logging
from decimal import Decimal
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
import openpyxl

from app.models import Alumno, Asistencia, Grupo, Upload
from app.models.semestres import Semestre, Horario, GrupoSemestre, UploadsHorario
from app.services.excel_parser import ParsedGrupo, parse_excel, leer_meta
from app.schemas import UploadUpsertResponse

logger = logging.getLogger(__name__)

def _get_decimal(summary: dict, key: str):
    v = summary.get(key)
    return Decimal(str(v)) if v is not None else None

def process_upload(
    db: Session,
    filename: str,
    file_bytes: bytes,
) -> UploadUpsertResponse:
    """
    Persist an uploaded Excel file using smart Upsert based on the _meta sheet.
    """
    # 1. Leer metadata
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        meta = leer_meta(wb)
        semestre_id = meta["semestre_id"]
        horario_id = meta["horario_id"]
    except Exception as e:
        logger.error(f"Error al leer metadata del excel: {e}")
        raise HTTPException(
            status_code=400, 
            detail="El archivo no es una plantilla válida del sistema. Descarga la plantilla desde el módulo de semestres."
        )

    # 2. Validar semestre activo
    semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
    if not semestre:
        raise HTTPException(status_code=400, detail="El semestre asociado a esta plantilla no existe.")
    if not semestre.activo:
        raise HTTPException(status_code=400, detail="El semestre asociado a esta plantilla no está activo.")

    horario = db.query(Horario).filter(Horario.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=400, detail="El horario asociado a esta plantilla no existe.")

    # 3. Obtener o crear registro en uploads_horario
    uh = db.query(UploadsHorario).filter(
        UploadsHorario.semestre_id == semestre_id,
        UploadsHorario.horario_id == horario_id
    ).first()
    if not uh:
        uh = UploadsHorario(semestre_id=semestre_id, horario_id=horario_id)
        db.add(uh)
        db.flush()

    # Parsear excel con el parser original (ignorará metadata oculta y parsing viejo sirve)
    try:
        parsed_grupos = parse_excel(file_bytes, semestre_label="")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not parsed_grupos:
        raise HTTPException(status_code=400, detail="El archivo no contiene hojas con el formato esperado.")

    # 4. Verificar fechas — doble check
    fecha_maxima_excel = None
    columnas_con_datos = set()

    for pg in parsed_grupos:
        for alumno_data in pg.alumnos:
            for iso_date, valor in alumno_data["dates"].items():
                if float(valor) > 0:
                    d = date.fromisoformat(iso_date)
                    columnas_con_datos.add(d)
                    if fecha_maxima_excel is None or d > fecha_maxima_excel:
                        fecha_maxima_excel = d

    if uh.ultima_fecha_subida and fecha_maxima_excel and fecha_maxima_excel < uh.ultima_fecha_subida:
        # 9. Para mantener compatibilidad, guardar Upload aunque no haya nuevas
        upload = Upload(filename=filename, semestre_id=semestre_id, horario_id=horario_id)
        db.add(upload)
        db.commit()
        return UploadUpsertResponse(
            upload_id=upload.id,
            semestre_id=semestre_id,
            semestre_nombre=semestre.nombre,
            horario_id=horario_id,
            horario_nombre=horario.nombre,
            actualizado=False,
            ultima_fecha_subida=uh.ultima_fecha_subida,
            hojas_procesadas=0,
            hojas_saltadas=0,
            total_alumnos=0,
            asistencias_nuevas=0,
            asistencias_protegidas=0,
            warning=f"No se encontraron fechas nuevas. El último upload registrado es del {uh.ultima_fecha_subida}. Verifica que estás subiendo la versión más reciente."
        )

    # 5. Filtrar columnas a procesar
    fechas_a_procesar = set()
    for d in columnas_con_datos:
        if not uh.ultima_fecha_subida or d >= uh.ultima_fecha_subida:
            fechas_a_procesar.add(d)

    # Variables de control
    hojas_procesadas = 0
    hojas_saltadas = 0
    total_alumnos = 0
    asistencias_nuevas = 0
    asistencias_protegidas = 0
    alumnos_nuevos_list = []
    alumnos_no_encontrados_list = []
    
    # Trackers para detectar bajas por grupo
    # {grupo_id: set(matriculas_excel)}
    matriculas_por_grupo = {}

    # 6. Upsert de alumnos & 7. Upsert de asistencias
    for pg in parsed_grupos:
        grupo_semestre = db.query(GrupoSemestre).filter(
            GrupoSemestre.semestre_id == semestre_id,
            GrupoSemestre.horario_id == horario_id,
            func.lower(func.trim(GrupoSemestre.nombre)) == pg.nombre.strip().lower()
        ).first()

        if not grupo_semestre:
            logger.warning(f"Grupo '{pg.nombre}' no encontrado para horario_id {horario_id}. Saltando.")
            hojas_saltadas += 1
            continue

        hojas_procesadas += 1
        matriculas_por_grupo[grupo_semestre.id] = set()

        for alumno_data in pg.alumnos:
            meta = alumno_data.get("meta", {})
            summary = alumno_data.get("summary", {})
            dates = alumno_data.get("dates", {})

            matricula = meta.get("matricula")
            if not matricula: # Si no hay matrícula, no podemos hacer Upsert confiable
                continue

            total_alumnos += 1
            matriculas_por_grupo[grupo_semestre.id].add(matricula)

            # Buscar alumno existente
            alumno = db.query(Alumno).filter(
                Alumno.matricula == matricula,
                Alumno.grupo_semestre_id == grupo_semestre.id
            ).first()

            if alumno:
                # Actualizar campos que pudieron cambiar (o sumarios semanales)
                if meta.get("carrera"):
                    alumno.carrera = meta.get("carrera")
                if meta.get("nombre"):
                    alumno.nombre = meta.get("nombre")
                if meta.get("folio"):
                    alumno.folio = meta.get("folio")
                
                alumno.total_asistencia = _get_decimal(summary, "ASISTENCIA")
                alumno.nutricion = _get_decimal(summary, "NUTRICIÓN")
                alumno.fisio = _get_decimal(summary, "FISIO")
                alumno.limpieza = _get_decimal(summary, "LIMPIEZA")
                alumno.coae = _get_decimal(summary, "COAE")
                alumno.taller = _get_decimal(summary, "TALLER")
                alumno.total = _get_decimal(summary, "TOTAL")
                # Siempre reactivar si viene en el Excel
                alumno.activo = True
            else:
                alumno = Alumno(
                    grupo_id=None, # Ya no usa grupo temporal
                    grupo_semestre_id=grupo_semestre.id,
                    folio=meta.get("folio"),
                    nombre=meta.get("nombre"),
                    matricula=matricula,
                    semestre=meta.get("semestre"),
                    carrera=meta.get("carrera"),
                    total_asistencia=_get_decimal(summary, "ASISTENCIA"),
                    nutricion=_get_decimal(summary, "NUTRICIÓN"),
                    fisio=_get_decimal(summary, "FISIO"),
                    limpieza=_get_decimal(summary, "LIMPIEZA"),
                    coae=_get_decimal(summary, "COAE"),
                    taller=_get_decimal(summary, "TALLER"),
                    total=_get_decimal(summary, "TOTAL"),
                    activo=True
                )
                db.add(alumno)
                alumnos_nuevos_list.append({"matricula": matricula, "nombre": meta.get("nombre") or "Sin nombre"})
            
            db.flush() # para obtener alumno.id si es nuevo

            for iso_date, valor in dates.items():
                d = date.fromisoformat(iso_date)
                if d not in fechas_a_procesar:
                    continue

                val = Decimal(str(valor))

                # Buscar si existe registro en asistencias
                asistencia = db.query(Asistencia).filter(
                    Asistencia.alumno_id == alumno.id,
                    Asistencia.fecha == d
                ).first()

                # No crear nuevos registros con 0 para fechas vacías del template.
                # El 0 solo se persiste si ya existía una asistencia previa.
                if val == 0 and not asistencia:
                    continue

                if asistencia:
                    if uh.ultima_fecha_subida and d < uh.ultima_fecha_subida:
                        asistencias_protegidas += 1
                        continue
                    
                    if asistencia.valor != val:
                        asistencia.valor = val
                        asistencias_nuevas += 1
                else:
                    db.add(Asistencia(alumno_id=alumno.id, fecha=d, valor=val))
                    if val > 0:
                        asistencias_nuevas += 1

    # Fase de detección de bajas: Alumnos en BD que no vinieron en Excel
    for g_id, matriculas_excel in matriculas_por_grupo.items():
        alumnos_bd = db.query(Alumno).filter(
            Alumno.grupo_semestre_id == g_id,
            Alumno.activo == True
        ).all()

        for a in alumnos_bd:
            if a.matricula not in matriculas_excel:
                alumnos_no_encontrados_list.append({"matricula": a.matricula, "nombre": a.nombre})

    # 8. Actualizar uploads_horario
    if fecha_maxima_excel:
        uh.ultima_fecha_subida = fecha_maxima_excel
    uh.ultimo_upload_at = func.now()
    uh.total_alumnos = total_alumnos

    # 9. Registrar en tabla uploads existente (Mantener compatibilidad)
    upload = Upload(filename=filename, semestre_id=semestre_id, horario_id=horario_id)
    db.add(upload)
    db.commit()

    return UploadUpsertResponse(
        upload_id=upload.id,
        semestre_id=semestre_id,
        semestre_nombre=semestre.nombre,
        horario_id=horario_id,
        horario_nombre=horario.nombre,
        actualizado=True,
        ultima_fecha_subida=uh.ultima_fecha_subida,
        hojas_procesadas=hojas_procesadas,
        hojas_saltadas=hojas_saltadas,
        total_alumnos=total_alumnos,
        asistencias_nuevas=asistencias_nuevas,
        asistencias_protegidas=asistencias_protegidas,
        alumnos_nuevos=alumnos_nuevos_list,
        alumnos_no_encontrados=alumnos_no_encontrados_list,
        warning=None
    )
