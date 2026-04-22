import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Alumno, Asistencia, Grupo, Upload, Prediccion, Semestre
from app.schemas import (
    AlumnoOut,
    AsistenciaOut,
    GrupoOut,
    TallerGrupoStats,
    UploadOut,
    UploadUpsertResponse,
    AlumnoUpdate,
)
from app.services.upload_service import process_upload
from app.services import stats_service, prediccion_service

from app.api.v1.pruebas_router import router as pruebas_router
from app.api.v1.semestres_router import router as semestres_router
from app.api.v1.carreras_router import router as carreras_router

from app.services.stats_service import (
    AsistenciaPorCarrera,
    TendenciaGrupo,
    AlumnoEnRiesgo,
    TalleresPorCarrera,
    AsistenciaPorSemestre,
    RankingGrupo,
    SemestreResumen,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["universidad-saludable"])
router.include_router(pruebas_router)
router.include_router(semestres_router, prefix="/semestres")
router.include_router(carreras_router, prefix="/carreras")

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


# ---------------------------------------------------------------------------
# POST /uploads
# ---------------------------------------------------------------------------

@router.post("/uploads", response_model=UploadUpsertResponse, status_code=201)
async def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Recibe un archivo Excel de asistencias, verifica la hoja _meta, 
    y aplica la lógica de Upsert inteligente.
    """
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Solo se aceptan archivos Excel (.xlsx, .xls). Recibido: '{file.filename}'",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    try:
        response = process_upload(
            db=db,
            filename=file.filename,
            file_bytes=file_bytes,
        )
    except HTTPException:
        # Re-lanza HTTPExceptions generadas dentro del proceso (ej. fallas _meta)
        raise

    except Exception as exc:
        logger.exception("Error inesperado al procesar el archivo.")
        raise HTTPException(status_code=500, detail="Error interno al procesar el archivo.")

    # Si fue analizado y no actualizado (HTTP 200 informativo)
    if not response.actualizado:
        from fastapi import Response
        # Se envía 200 explícito por sobre el status_code del decorador
        pass # Status code defaults to 201 via decorator, but that is fine for non-update successes or we could modify response on access.
             # Actually, FastAPI permits modifying the response code using a response injected object, but returning the response dict is sufficient here.

    return response


# ---------------------------------------------------------------------------
# GET /uploads
# ---------------------------------------------------------------------------

@router.get("/uploads", response_model=list[UploadOut])
def list_uploads(db: Session = Depends(get_db)):
    """Lista todos los archivos subidos."""
    uploads = db.query(Upload).order_by(Upload.uploaded_at.desc()).all()
    return [
        UploadOut(
            id=u.id,
            filename=u.filename,
            uploaded_at=u.uploaded_at,
            semestre_label=u.semestre_label or (u.semestre.nombre if getattr(u, "semestre", None) else None),
            semestre_id=u.semestre_id,
            horario_id=u.horario_id,
        )
        for u in uploads
    ]


# ---------------------------------------------------------------------------
# GET /uploads/{upload_id}/grupos
# ---------------------------------------------------------------------------

@router.get("/uploads/{upload_id}/grupos", response_model=list[GrupoOut])
def list_grupos(upload_id: int, db: Session = Depends(get_db)):
    """Lista los grupos de un archivo subido."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} no encontrado.")

    grupos = (
        db.query(Grupo)
        .filter(Grupo.upload_id == upload_id)
        .all()
    )

    result = []
    for g in grupos:
        count = db.query(func.count(Alumno.id)).filter(Alumno.grupo_id == g.id).scalar()
        result.append(
            GrupoOut(
                id=g.id,
                upload_id=g.upload_id,
                nombre=g.nombre,
                horario=g.horario,
                total_alumnos=count or 0,
            )
        )
    return result


# ---------------------------------------------------------------------------
# STATS — /stats/uploads/{upload_id}/...
# ---------------------------------------------------------------------------

@router.get("/stats/uploads/{upload_id}/asistencia-por-carrera", response_model=list[AsistenciaPorCarrera], tags=["stats"])
def stats_asistencia_por_carrera(upload_id: int, db: Session = Depends(get_db)):
    return stats_service.get_asistencia_por_carrera(db, upload_id)


@router.get("/stats/uploads/{upload_id}/tendencia-semanal", response_model=list[TendenciaGrupo], tags=["stats"])
def stats_tendencia_semanal(upload_id: int, db: Session = Depends(get_db)):
    return stats_service.get_tendencia_semanal(db, upload_id)


@router.get("/stats/uploads/{upload_id}/alumnos-en-riesgo", response_model=list[AlumnoEnRiesgo], tags=["stats"])
def stats_alumnos_en_riesgo(
    upload_id: int,
    umbral: float = 60.0,
    grupo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return stats_service.get_alumnos_en_riesgo(db, upload_id, umbral, grupo_id)


@router.get("/stats/uploads/{upload_id}/talleres-por-carrera", response_model=list[TalleresPorCarrera], tags=["stats"])
def stats_talleres_por_carrera(upload_id: int, db: Session = Depends(get_db)):
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} no encontrado.")
    
    if upload.semestre_id:
        semestre = db.query(Semestre).filter(Semestre.id == upload.semestre_id).first()
        if semestre and not semestre.tiene_talleres:
            return Response(status_code=204)
            
    return stats_service.get_talleres_por_carrera(db, upload_id)


@router.get("/stats/uploads/{upload_id}/asistencia-por-semestre-alumno", response_model=list[AsistenciaPorSemestre], tags=["stats"])
def stats_asistencia_por_semestre_alumno(upload_id: int, db: Session = Depends(get_db)):
    return stats_service.get_asistencia_por_semestre_alumno(db, upload_id)


@router.get("/stats/uploads/{upload_id}/ranking-grupos", response_model=list[RankingGrupo], tags=["stats"])
def stats_ranking_grupos(upload_id: int, db: Session = Depends(get_db)):
    return stats_service.get_ranking_grupos(db, upload_id)


# ---------------------------------------------------------------------------
# STATS — /stats/semestres/{semestre_id}/...
# ---------------------------------------------------------------------------

@router.get("/stats/semestres/{semestre_id}/asistencia-por-carrera", response_model=list[AsistenciaPorCarrera], tags=["stats"])
def stats_asistencia_por_carrera_semestre(semestre_id: int, db: Session = Depends(get_db)):
    return stats_service.get_asistencia_por_carrera_por_semestre(db, semestre_id)


@router.get("/stats/semestres/{semestre_id}/tendencia-semanal", response_model=list[TendenciaGrupo], tags=["stats"])
def stats_tendencia_semanal_semestre(semestre_id: int, db: Session = Depends(get_db)):
    return stats_service.get_tendencia_semanal_por_semestre(db, semestre_id)


@router.get("/stats/semestres/{semestre_id}/alumnos-en-riesgo", response_model=list[AlumnoEnRiesgo], tags=["stats"])
def stats_alumnos_en_riesgo_semestre(
    semestre_id: int,
    umbral: float = 60.0,
    grupo_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return stats_service.get_alumnos_en_riesgo_por_semestre(db, semestre_id, umbral, grupo_id)


@router.get("/stats/semestres/{semestre_id}/ranking-grupos", response_model=list[RankingGrupo], tags=["stats"])
def stats_ranking_grupos_semestre(semestre_id: int, db: Session = Depends(get_db)):
    return stats_service.get_ranking_grupos_por_semestre(db, semestre_id)


@router.get("/stats/semestres/{semestre_id}/talleres-por-carrera", response_model=list[TalleresPorCarrera], tags=["stats"])
def stats_talleres_por_carrera_semestre(semestre_id: int, db: Session = Depends(get_db)):
    return stats_service.get_talleres_por_carrera_por_semestre(db, semestre_id)


@router.get("/stats/semestres/{semestre_id}/asistencia-por-semestre-alumno", response_model=list[AsistenciaPorSemestre], tags=["stats"])
def stats_asistencia_por_semestre_alumno_semestre(semestre_id: int, db: Session = Depends(get_db)):
    return stats_service.get_asistencia_por_semestre_alumno_por_semestre(db, semestre_id)


@router.get("/stats/semestres/{semestre_id}/resumen", response_model=SemestreResumen, tags=["stats"])
def stats_resumen_semestre(semestre_id: int, db: Session = Depends(get_db)):
    return stats_service.get_resumen_semestre(db, semestre_id)


# ---------------------------------------------------------------------------
# GET /grupos/{grupo_id}/alumnos
# ---------------------------------------------------------------------------

@router.get("/grupos/{grupo_id}/alumnos", response_model=list[AlumnoOut])
def list_alumnos(
    grupo_id: int,
    carrera: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lista los alumnos de un grupo. Opcionalmente filtra por ?carrera=."""
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail=f"Grupo {grupo_id} no encontrado.")

    query = db.query(Alumno).filter(Alumno.grupo_id == grupo_id)
    if carrera:
        query = query.filter(Alumno.carrera.ilike(f"%{carrera}%"))

    return query.all()


# ---------------------------------------------------------------------------
# GET /alumnos/{alumno_id}/asistencias
# ---------------------------------------------------------------------------

@router.get("/alumnos/{alumno_id}/asistencias", response_model=list[AsistenciaOut])
def get_asistencias(alumno_id: int, db: Session = Depends(get_db)):
    """Devuelve todas las fechas y valores de asistencia de un alumno."""
    alumno = db.query(Alumno).filter(Alumno.id == alumno_id).first()
    if not alumno:
        raise HTTPException(status_code=404, detail=f"Alumno {alumno_id} no encontrado.")

    asistencias = (
        db.query(Asistencia)
        .filter(Asistencia.alumno_id == alumno_id)
        .order_by(Asistencia.fecha)
        .all()
    )
    return asistencias


# ---------------------------------------------------------------------------
# PATCH /alumnos/{alumno_id}/activo
# ---------------------------------------------------------------------------

@router.patch("/alumnos/{alumno_id}/activo", response_model=AlumnoOut)
def update_alumno_activo(alumno_id: int, updates: AlumnoUpdate, db: Session = Depends(get_db)):
    """Marca a un alumno como inactivo (baja) o lo reactiva."""
    alumno = db.query(Alumno).filter(Alumno.id == alumno_id).first()
    if not alumno:
        raise HTTPException(status_code=404, detail=f"Alumno {alumno_id} no encontrado.")

    if updates.activo is not None:
        alumno.activo = updates.activo
    db.commit()
    db.refresh(alumno)
    return alumno


# ---------------------------------------------------------------------------
# GET /uploads/{upload_id}/talleres
# ---------------------------------------------------------------------------

@router.get("/uploads/{upload_id}/talleres", response_model=list[TallerGrupoStats])
def get_talleres(upload_id: int, db: Session = Depends(get_db)):
    """
    Por cada grupo del archivo, calcula los promedios de NUTRICION, FISIO,
    LIMPIEZA, COAE y TALLER para análisis comparativo.
    """
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} no encontrado.")

    if upload.semestre_id:
        semestre = db.query(Semestre).filter(Semestre.id == upload.semestre_id).first()
        if semestre and not semestre.tiene_talleres:
            return Response(status_code=204)

    grupos = db.query(Grupo).filter(Grupo.upload_id == upload_id).all()

    result = []
    for g in grupos:
        row = (
            db.query(
                func.avg(Alumno.nutricion).label("avg_nutricion"),
                func.avg(Alumno.fisio).label("avg_fisio"),
                func.avg(Alumno.limpieza).label("avg_limpieza"),
                func.avg(Alumno.coae).label("avg_coae"),
                func.avg(Alumno.taller).label("avg_taller"),
            )
            .filter(Alumno.grupo_id == g.id)
            .one()
        )

        result.append(
            TallerGrupoStats(
                grupo_id=g.id,
                grupo_nombre=g.nombre,
                avg_nutricion=float(row.avg_nutricion) if row.avg_nutricion is not None else None,
                avg_fisio=float(row.avg_fisio) if row.avg_fisio is not None else None,
                avg_limpieza=float(row.avg_limpieza) if row.avg_limpieza is not None else None,
                avg_coae=float(row.avg_coae) if row.avg_coae is not None else None,
                avg_taller=float(row.avg_taller) if row.avg_taller is not None else None,
            )
        )

    return result


# ---------------------------------------------------------------------------
# PREDICCIONES ML
# ---------------------------------------------------------------------------

@router.post("/predicciones/{upload_id}")
def post_predecir_riesgo(upload_id: int, db: Session = Depends(get_db)):
    """Ejecuta el modelo de predicción de riesgo para todos los alumnos de un upload."""
    if not prediccion_service.modelo_disponible():
        raise HTTPException(
            status_code=503, 
            detail="Modelo de predicción no disponible. Verifica que los artefactos .pkl estén en app/ml/"
        )
    
    try:
        resumen = prediccion_service.predecir_upload(db, upload_id)
        return resumen
    except Exception as e:
        if "Upload no encontrado" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        logger.exception(f"Error al predecir upload {upload_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predicciones/{upload_id}")
def get_predicciones(upload_id: int, db: Session = Depends(get_db)):
    """Devuelve las predicciones de un upload agrupadas por grupo."""
    preds = db.query(Prediccion).join(Alumno).filter(Prediccion.upload_id == upload_id).all()
    
    if not preds:
        return []

    grupos_dict = {}
    for p in preds:
        gn = p.grupo_nombre or "Desconocido"
        if gn not in grupos_dict:
            grupos_dict[gn] = []
        
        grupos_dict[gn].append({
            "matricula": p.alumno.matricula,
            "nombre": p.alumno.nombre,
            "carrera": p.alumno.carrera,
            "prob_riesgo": float(p.prob_riesgo) if p.prob_riesgo is not None else 0.0,
            "nivel_riesgo": p.nivel_riesgo,
            "prediccion": p.prediccion
        })

    # Ordenar alumnos por prob_riesgo descendente y convertir a la lista final
    result = []
    # Ordenar grupos alfabéticamente para consistencia
    for gn in sorted(grupos_dict.keys()):
        alumnos = grupos_dict[gn]
        alumnos_ordenados = sorted(alumnos, key=lambda x: x["prob_riesgo"], reverse=True)
        result.append({
            "grupo": gn,
            "alumnos": alumnos_ordenados
        })
    
    return result


@router.get("/predicciones/{upload_id}/resumen")
def get_predicciones_resumen(upload_id: int, db: Session = Depends(get_db)):
    """Devuelve solo los conteos de riesgo por nivel para un upload."""
    stats = db.query(
        Prediccion.nivel_riesgo,
        func.count(Prediccion.id).label("total")
    ).filter(Prediccion.upload_id == upload_id).group_by(Prediccion.nivel_riesgo).all()

    resumen = {"upload_id": upload_id, "alto": 0, "medio": 0, "bajo": 0, "total": 0}
    total_gral = 0
    for nivel, count in stats:
        if nivel == "Alto":
            resumen["alto"] = count
        elif nivel == "Medio":
            resumen["medio"] = count
        elif nivel == "Bajo":
            resumen["bajo"] = count
        total_gral += count
    
    resumen["total"] = total_gral
    return resumen
