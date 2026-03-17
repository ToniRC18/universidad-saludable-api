from datetime import date
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Alumno, Asistencia, Grupo, Upload

MAX_ASISTENCIA = 60.0  # 24 sesiones × 2.5 pts


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class AsistenciaPorCarrera(BaseModel):
    carrera: str
    total_alumnos: int
    promedio_asistencia: float
    promedio_porcentaje: float


class PuntoTendencia(BaseModel):
    semana: int
    fecha_inicio: date
    promedio: float


class TendenciaGrupo(BaseModel):
    grupo: str
    tendencia: list[PuntoTendencia]


class AlumnoEnRiesgo(BaseModel):
    alumno_id: int
    nombre: Optional[str]
    matricula: Optional[str]
    carrera: Optional[str]
    grupo: str
    asistencia_total: float
    porcentaje: float


class TalleresPorCarrera(BaseModel):
    carrera: str
    nutricion: Optional[float]
    fisio: Optional[float]
    limpieza: Optional[float]
    coae: Optional[float]
    taller: Optional[float]


class AsistenciaPorSemestre(BaseModel):
    semestre: str
    total_alumnos: int
    promedio_asistencia: float
    promedio_porcentaje: float


class RankingGrupo(BaseModel):
    grupo_id: int
    grupo: str
    total_alumnos: int
    promedio_asistencia: float
    porcentaje: float
    posicion: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_upload_or_404(db: Session, upload_id: int) -> Upload:
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} no encontrado.")
    return upload


def _r(v) -> Optional[float]:
    return round(float(v), 1) if v is not None else None


# ---------------------------------------------------------------------------
# 1. Asistencia por carrera
# ---------------------------------------------------------------------------

def get_asistencia_por_carrera(db: Session, upload_id: int) -> list[AsistenciaPorCarrera]:
    _get_upload_or_404(db, upload_id)

    rows = (
        db.query(
            Alumno.carrera,
            func.count(Alumno.id).label("total_alumnos"),
            func.avg(Alumno.total_asistencia).label("promedio"),
        )
        .join(Grupo, Alumno.grupo_id == Grupo.id)
        .filter(Grupo.upload_id == upload_id, Alumno.carrera.isnot(None))
        .group_by(Alumno.carrera)
        .order_by(func.avg(Alumno.total_asistencia).desc())
        .all()
    )

    result = []
    for row in rows:
        promedio = round(float(row.promedio or 0), 1)
        result.append(AsistenciaPorCarrera(
            carrera=row.carrera,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            promedio_porcentaje=round((promedio / MAX_ASISTENCIA) * 100, 1),
        ))
    return result


# ---------------------------------------------------------------------------
# 2. Tendencia semanal
# ---------------------------------------------------------------------------

def get_tendencia_semanal(db: Session, upload_id: int) -> list[TendenciaGrupo]:
    _get_upload_or_404(db, upload_id)

    grupos = db.query(Grupo).filter(Grupo.upload_id == upload_id).all()

    result = []
    for grupo in grupos:
        fechas = (
            db.query(Asistencia.fecha)
            .join(Alumno, Asistencia.alumno_id == Alumno.id)
            .filter(Alumno.grupo_id == grupo.id)
            .distinct()
            .order_by(Asistencia.fecha)
            .all()
        )
        fechas = [f[0] for f in fechas]

        if not fechas:
            continue

        tendencia = []
        for i in range(0, len(fechas), 2):
            semana_fechas = fechas[i : i + 2]
            avg_val = (
                db.query(func.avg(Asistencia.valor))
                .join(Alumno, Asistencia.alumno_id == Alumno.id)
                .filter(Alumno.grupo_id == grupo.id, Asistencia.fecha.in_(semana_fechas))
                .scalar()
            )
            tendencia.append(PuntoTendencia(
                semana=(i // 2) + 1,
                fecha_inicio=semana_fechas[0],
                promedio=round(float(avg_val or 0), 1),
            ))

        result.append(TendenciaGrupo(grupo=grupo.nombre, tendencia=tendencia))

    return result


# ---------------------------------------------------------------------------
# 3. Alumnos en riesgo
# ---------------------------------------------------------------------------

def get_alumnos_en_riesgo(
    db: Session,
    upload_id: int,
    umbral: float = 60.0,
    grupo_id: Optional[int] = None,
) -> list[AlumnoEnRiesgo]:
    _get_upload_or_404(db, upload_id)

    query = (
        db.query(Alumno, Grupo.nombre.label("grupo_nombre"))
        .join(Grupo, Alumno.grupo_id == Grupo.id)
        .filter(Grupo.upload_id == upload_id, Alumno.total_asistencia.isnot(None))
    )

    if grupo_id is not None:
        query = query.filter(Alumno.grupo_id == grupo_id)

    result = []
    for alumno, grupo_nombre in query.all():
        asistencia = float(alumno.total_asistencia)
        porcentaje = round((asistencia / MAX_ASISTENCIA) * 100, 1)
        if porcentaje < umbral:
            result.append(AlumnoEnRiesgo(
                alumno_id=alumno.id,
                nombre=alumno.nombre,
                matricula=alumno.matricula,
                carrera=alumno.carrera,
                grupo=grupo_nombre,
                asistencia_total=round(asistencia, 1),
                porcentaje=porcentaje,
            ))

    result.sort(key=lambda x: x.porcentaje)
    return result


# ---------------------------------------------------------------------------
# 4. Talleres por carrera
# ---------------------------------------------------------------------------

def get_talleres_por_carrera(db: Session, upload_id: int) -> list[TalleresPorCarrera]:
    _get_upload_or_404(db, upload_id)

    rows = (
        db.query(
            Alumno.carrera,
            func.avg(Alumno.nutricion).label("nutricion"),
            func.avg(Alumno.fisio).label("fisio"),
            func.avg(Alumno.limpieza).label("limpieza"),
            func.avg(Alumno.coae).label("coae"),
            func.avg(Alumno.taller).label("taller"),
        )
        .join(Grupo, Alumno.grupo_id == Grupo.id)
        .filter(Grupo.upload_id == upload_id, Alumno.carrera.isnot(None))
        .group_by(Alumno.carrera)
        .all()
    )

    return [
        TalleresPorCarrera(
            carrera=row.carrera,
            nutricion=_r(row.nutricion),
            fisio=_r(row.fisio),
            limpieza=_r(row.limpieza),
            coae=_r(row.coae),
            taller=_r(row.taller),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 5. Asistencia por semestre del alumno
# ---------------------------------------------------------------------------

def get_asistencia_por_semestre_alumno(db: Session, upload_id: int) -> list[AsistenciaPorSemestre]:
    _get_upload_or_404(db, upload_id)

    rows = (
        db.query(
            Alumno.semestre,
            func.count(Alumno.id).label("total_alumnos"),
            func.avg(Alumno.total_asistencia).label("promedio"),
        )
        .join(Grupo, Alumno.grupo_id == Grupo.id)
        .filter(Grupo.upload_id == upload_id, Alumno.semestre.isnot(None))
        .group_by(Alumno.semestre)
        .order_by(Alumno.semestre)
        .all()
    )

    result = []
    for row in rows:
        promedio = round(float(row.promedio or 0), 1)
        result.append(AsistenciaPorSemestre(
            semestre=row.semestre,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            promedio_porcentaje=round((promedio / MAX_ASISTENCIA) * 100, 1),
        ))
    return result


# ---------------------------------------------------------------------------
# 6. Ranking de grupos
# ---------------------------------------------------------------------------

def get_ranking_grupos(db: Session, upload_id: int) -> list[RankingGrupo]:
    _get_upload_or_404(db, upload_id)

    rows = (
        db.query(
            Grupo.id,
            Grupo.nombre,
            func.count(Alumno.id).label("total_alumnos"),
            func.avg(Alumno.total_asistencia).label("promedio"),
        )
        .join(Alumno, Alumno.grupo_id == Grupo.id)
        .filter(Grupo.upload_id == upload_id)
        .group_by(Grupo.id, Grupo.nombre)
        .order_by(func.avg(Alumno.total_asistencia).desc())
        .all()
    )

    result = []
    for pos, row in enumerate(rows, start=1):
        promedio = round(float(row.promedio or 0), 1)
        result.append(RankingGrupo(
            grupo_id=row.id,
            grupo=row.nombre,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            porcentaje=round((promedio / MAX_ASISTENCIA) * 100, 1),
            posicion=pos,
        ))
    return result
