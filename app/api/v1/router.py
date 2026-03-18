import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Alumno, Asistencia, Grupo, Upload
from app.schemas import (
    AlumnoOut,
    AsistenciaOut,
    GrupoOut,
    TallerGrupoStats,
    UploadOut,
    UploadSummary,
)
from app.services.upload_service import process_upload
from app.services import stats_service
from app.api.v1.pruebas_router import router as pruebas_router
from app.services.stats_service import (
    AsistenciaPorCarrera,
    TendenciaGrupo,
    AlumnoEnRiesgo,
    TalleresPorCarrera,
    AsistenciaPorSemestre,
    RankingGrupo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["universidad-saludable"])
router.include_router(pruebas_router)

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


# ---------------------------------------------------------------------------
# POST /uploads
# ---------------------------------------------------------------------------

@router.post("/uploads", response_model=UploadSummary, status_code=201)
async def upload_excel(
    file: UploadFile = File(...),
    semestre_label: str = Form(""),
    db: Session = Depends(get_db),
):
    """Recibe un archivo Excel de asistencias, lo parsea y persiste en BD."""
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
        upload, parsed_grupos = process_upload(
            db=db,
            filename=file.filename,
            file_bytes=file_bytes,
            semestre_label=semestre_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Error inesperado al procesar el archivo.")
        raise HTTPException(status_code=500, detail="Error interno al procesar el archivo.")

    total_alumnos = sum(len(g.alumnos) for g in parsed_grupos)

    return UploadSummary(
        id=upload.id,
        filename=upload.filename,
        uploaded_at=upload.uploaded_at,
        semestre_label=upload.semestre_label,
        grupos_found=len(parsed_grupos),
        total_alumnos=total_alumnos,
    )


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
            semestre_label=u.semestre_label,
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
    return stats_service.get_talleres_por_carrera(db, upload_id)


@router.get("/stats/uploads/{upload_id}/asistencia-por-semestre-alumno", response_model=list[AsistenciaPorSemestre], tags=["stats"])
def stats_asistencia_por_semestre_alumno(upload_id: int, db: Session = Depends(get_db)):
    return stats_service.get_asistencia_por_semestre_alumno(db, upload_id)


@router.get("/stats/uploads/{upload_id}/ranking-grupos", response_model=list[RankingGrupo], tags=["stats"])
def stats_ranking_grupos(upload_id: int, db: Session = Depends(get_db)):
    return stats_service.get_ranking_grupos(db, upload_id)


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
