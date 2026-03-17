import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Alumno, Asistencia, Grupo, Upload
from app.services.excel_parser import ParsedGrupo, parse_excel

logger = logging.getLogger(__name__)


def process_upload(
    db: Session,
    filename: str,
    file_bytes: bytes,
    semestre_label: str = "",
) -> tuple[Upload, list[ParsedGrupo]]:
    """
    Persist an uploaded Excel file into the database.
    Returns the Upload ORM object and the list of parsed grupos.
    """
    parsed_grupos = parse_excel(file_bytes, semestre_label=semestre_label)

    if not parsed_grupos:
        raise ValueError("El archivo no contiene hojas con el formato esperado.")

    upload = Upload(filename=filename, semestre_label=semestre_label or None)
    db.add(upload)
    db.flush()  # get upload.id

    for pg in parsed_grupos:
        grupo = Grupo(upload_id=upload.id, nombre=pg.nombre, horario=pg.horario or None)
        db.add(grupo)
        db.flush()  # get grupo.id

        for alumno_data in pg.alumnos:
            meta = alumno_data.get("meta", {})
            summary = alumno_data.get("summary", {})
            dates = alumno_data.get("dates", {})

            def _dec(key: str):
                v = summary.get(key)
                return Decimal(str(v)) if v is not None else None

            alumno = Alumno(
                grupo_id=grupo.id,
                folio=meta.get("folio"),
                nombre=meta.get("nombre"),
                matricula=meta.get("matricula"),
                semestre=meta.get("semestre"),
                carrera=meta.get("carrera"),
                total_asistencia=_dec("ASISTENCIA"),
                nutricion=_dec("NUTRICIÓN"),
                fisio=_dec("FISIO"),
                limpieza=_dec("LIMPIEZA"),
                coae=_dec("COAE"),
                taller=_dec("TALLER"),
                total=_dec("TOTAL"),
            )
            db.add(alumno)
            db.flush()  # get alumno.id

            for iso_date, valor in dates.items():
                from datetime import date as date_type
                fecha = date_type.fromisoformat(iso_date)
                asistencia = Asistencia(
                    alumno_id=alumno.id,
                    fecha=fecha,
                    valor=Decimal(str(valor)),
                )
                db.add(asistencia)

    db.commit()
    db.refresh(upload)
    return upload, parsed_grupos
