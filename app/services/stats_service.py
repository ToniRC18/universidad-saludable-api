from datetime import date
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import Alumno, Asistencia, Grupo, Upload
from app.models.semestres import GrupoSemestre, Horario, Semestre

MAX_ASISTENCIA_FALLBACK = 60.0  # fallback para grupos sin max_asistencia (datos previos a la migración)


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


class HorarioResumenSemestre(BaseModel):
    horario_id: int
    nombre: str
    ultima_fecha_subida: Optional[date]
    total_alumnos: int
    porcentaje_asistencia: float


class SemestreResumen(BaseModel):
    semestre_id: int
    total_alumnos: int
    total_grupos: int
    porcentaje_asistencia_promedio: float
    alumnos_en_riesgo: int
    horarios: list[HorarioResumenSemestre]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_upload_or_404(db: Session, upload_id: int) -> Upload:
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail=f"Upload {upload_id} no encontrado.")
    return upload


def _get_semestre_or_404(db: Session, semestre_id: int) -> Semestre:
    semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
    if not semestre:
        raise HTTPException(status_code=404, detail=f"Semestre {semestre_id} no encontrado.")
    return semestre

def _r(v) -> Optional[float]:
    return round(float(v), 1) if v is not None else None

def _build_upload_match(upload: Upload):
    conditions = [Grupo.upload_id == upload.id]

    if upload.horario_id is not None:
        new_path_filters = [GrupoSemestre.horario_id == upload.horario_id]
        if upload.semestre_id is not None:
            new_path_filters.append(GrupoSemestre.semestre_id == upload.semestre_id)
        conditions.append(and_(Alumno.grupo_semestre_id.isnot(None), *new_path_filters))

    return or_(*conditions)


def _get_upload_alumnos_query(db: Session, upload: Upload, *entities):
    """
    Base query that supports both historical uploads (`grupo_id`) and the
    upsert model (`grupo_semestre_id`) without breaking backwards compatibility.
    """
    return (
        db.query(*entities)
        .outerjoin(Grupo, Alumno.grupo_id == Grupo.id)
        .outerjoin(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
        .outerjoin(Semestre, GrupoSemestre.semestre_id == Semestre.id)
        .filter(_build_upload_match(upload))
        .filter(Alumno.activo.is_(True))
    )


def _get_semestre_alumnos_query(db: Session, semestre_id: int, *entities):
    """
    Base query for semester-centric stats. Unlike upload-based stats, this only
    includes the new semester/horario model via GrupoSemestre -> Horario.
    """
    return (
        db.query(*entities)
        .join(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
        .join(Horario, GrupoSemestre.horario_id == Horario.id)
        .join(Semestre, GrupoSemestre.semestre_id == Semestre.id)
        .filter(GrupoSemestre.semestre_id == semestre_id)
        .filter(Horario.semestre_id == semestre_id)
        .filter(Alumno.activo.is_(True))
    )


def get_horario_registro_real(db: Session, semestre_id: int, horario_id: int) -> tuple[Optional[date], int]:
    """
    Return the last attendance date with real captured data for a semester horario
    and the number of completed weeks based on distinct dates with `valor > 0`.
    Template-generated zeros are ignored.
    """
    horario = (
        db.query(Horario)
        .filter(Horario.id == horario_id, Horario.semestre_id == semestre_id)
        .first()
    )
    dias_configurados = sum(
        1 for dia in [horario.dia_1, horario.dia_2, horario.dia_3, horario.dia_4]
        if dia is not None
    ) if horario else 0
    sesiones_por_semana = dias_configurados if dias_configurados > 0 else 2

    base_query = (
        db.query(Asistencia.fecha)
        .join(Alumno, Asistencia.alumno_id == Alumno.id)
        .join(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
        .filter(
            GrupoSemestre.horario_id == horario_id,
            GrupoSemestre.semestre_id == semestre_id,
            Asistencia.valor > 0,
            Alumno.activo.is_(True),
        )
    )

    ultima_fecha_real = db.query(func.max(Asistencia.fecha)).select_from(Asistencia).join(
        Alumno, Asistencia.alumno_id == Alumno.id
    ).join(
        GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id
    ).filter(
        GrupoSemestre.horario_id == horario_id,
        GrupoSemestre.semestre_id == semestre_id,
        Asistencia.valor > 0,
        Alumno.activo.is_(True),
    ).scalar()

    fechas_con_datos = base_query.distinct().count()
    semanas_registradas = fechas_con_datos // sesiones_por_semana

    return ultima_fecha_real, semanas_registradas


def _get_asistencia_totals_subquery(db: Session):
    return (
        db.query(
            Asistencia.alumno_id.label("alumno_id"),
            func.sum(Asistencia.valor).label("total_asistencia_calculada"),
        )
        .group_by(Asistencia.alumno_id)
        .subquery()
    )


def _get_upload_groups(db: Session, upload: Upload) -> list[tuple[str, int, str]]:
    groups: list[tuple[str, int, str]] = []

    historical = (
        db.query(Grupo.id, Grupo.nombre)
        .filter(Grupo.upload_id == upload.id)
        .order_by(Grupo.nombre)
        .all()
    )
    groups.extend(("historico", row.id, row.nombre) for row in historical)

    if upload.horario_id is not None:
        q = db.query(GrupoSemestre.id, GrupoSemestre.nombre).filter(
            GrupoSemestre.horario_id == upload.horario_id
        )
        if upload.semestre_id is not None:
            q = q.filter(GrupoSemestre.semestre_id == upload.semestre_id)
        groups.extend(("semestre", row.id, row.nombre) for row in q.order_by(GrupoSemestre.nombre).all())

    return groups


def _get_semestre_groups(db: Session, semestre_id: int) -> list[tuple[int, str]]:
    return (
        db.query(GrupoSemestre.id, GrupoSemestre.nombre)
        .filter(GrupoSemestre.semestre_id == semestre_id)
        .order_by(GrupoSemestre.nombre)
        .all()
    )


# ---------------------------------------------------------------------------
# 1. Asistencia por carrera
# ---------------------------------------------------------------------------

def get_asistencia_por_carrera(db: Session, upload_id: int) -> list[AsistenciaPorCarrera]:
    upload = _get_upload_or_404(db, upload_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    q = _get_upload_alumnos_query(
        db,
        upload,
        Alumno.carrera,
        func.count(Alumno.id).label("total_alumnos"),
        func.avg(total_asistencia_expr).label("promedio"),
        func.avg(func.coalesce(Semestre.puntaje_maximo_asistencia, Grupo.max_asistencia)).label("avg_max"),
    ).outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id).filter(Alumno.carrera.isnot(None))

    rows = q.group_by(Alumno.carrera).order_by(func.avg(total_asistencia_expr).desc()).all()

    result = []
    for row in rows:
        promedio = round(float(row.promedio or 0), 1)
        max_asis = float(row.avg_max) if row.avg_max else MAX_ASISTENCIA_FALLBACK
        result.append(AsistenciaPorCarrera(
            carrera=row.carrera,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            promedio_porcentaje=round((promedio / max_asis) * 100, 1) if max_asis else 0.0,
        ))
    return result


def get_asistencia_por_carrera_por_semestre(db: Session, semestre_id: int) -> list[AsistenciaPorCarrera]:
    _get_semestre_or_404(db, semestre_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    q = _get_semestre_alumnos_query(
        db,
        semestre_id,
        Alumno.carrera,
        func.count(Alumno.id).label("total_alumnos"),
        func.avg(total_asistencia_expr).label("promedio"),
        func.avg(Semestre.puntaje_maximo_asistencia).label("avg_max"),
    ).outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id).filter(Alumno.carrera.isnot(None))

    rows = q.group_by(Alumno.carrera).order_by(func.avg(total_asistencia_expr).desc()).all()

    result = []
    for row in rows:
        promedio = round(float(row.promedio or 0), 1)
        max_asis = float(row.avg_max) if row.avg_max else MAX_ASISTENCIA_FALLBACK
        result.append(AsistenciaPorCarrera(
            carrera=row.carrera,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            promedio_porcentaje=round((promedio / max_asis) * 100, 1) if max_asis else 0.0,
        ))
    return result


# ---------------------------------------------------------------------------
# 2. Tendencia semanal
# ---------------------------------------------------------------------------

def get_tendencia_semanal(db: Session, upload_id: int) -> list[TendenciaGrupo]:
    upload = _get_upload_or_404(db, upload_id)

    result = []
    for group_kind, group_id, group_name in _get_upload_groups(db, upload):
        q_fechas = (
            db.query(Asistencia.fecha)
            .join(Alumno, Asistencia.alumno_id == Alumno.id)
            .filter(Alumno.activo.is_(True))
        )
        if group_kind == "semestre":
            q_fechas = q_fechas.filter(Alumno.grupo_semestre_id == group_id)
        else:
            q_fechas = q_fechas.filter(Alumno.grupo_id == group_id)

        fechas = q_fechas.distinct().order_by(Asistencia.fecha).all()
        fechas = [f[0] for f in fechas]

        if not fechas:
            continue

        tendencia = []
        for i in range(0, len(fechas), 2):
            semana_fechas = fechas[i : i + 2]
            q_avg = db.query(func.avg(Asistencia.valor)).join(Alumno, Asistencia.alumno_id == Alumno.id)
            if group_kind == "semestre":
                q_avg = q_avg.filter(Alumno.grupo_semestre_id == group_id, Asistencia.fecha.in_(semana_fechas), Alumno.activo.is_(True))
            else:
                q_avg = q_avg.filter(Alumno.grupo_id == group_id, Asistencia.fecha.in_(semana_fechas), Alumno.activo.is_(True))
            
            avg_val = q_avg.scalar()
            
            tendencia.append(PuntoTendencia(
                semana=(i // 2) + 1,
                fecha_inicio=semana_fechas[0],
                promedio=round(float(avg_val or 0), 1),
            ))

        result.append(TendenciaGrupo(grupo=group_name, tendencia=tendencia))

    return result


def get_tendencia_semanal_por_semestre(db: Session, semestre_id: int) -> list[TendenciaGrupo]:
    _get_semestre_or_404(db, semestre_id)

    result = []
    for group_id, group_name in _get_semestre_groups(db, semestre_id):
        fechas = (
            db.query(Asistencia.fecha)
            .join(Alumno, Asistencia.alumno_id == Alumno.id)
            .filter(Alumno.grupo_semestre_id == group_id, Alumno.activo.is_(True))
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
                .filter(
                    Alumno.grupo_semestre_id == group_id,
                    Asistencia.fecha.in_(semana_fechas),
                    Alumno.activo.is_(True),
                )
                .scalar()
            )

            tendencia.append(PuntoTendencia(
                semana=(i // 2) + 1,
                fecha_inicio=semana_fechas[0],
                promedio=round(float(avg_val or 0), 1),
            ))

        result.append(TendenciaGrupo(grupo=group_name, tendencia=tendencia))

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
    upload = _get_upload_or_404(db, upload_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    q = _get_upload_alumnos_query(
        db,
        upload,
        Alumno,
        total_asistencia_expr.label("asistencia_total"),
        func.coalesce(GrupoSemestre.nombre, Grupo.nombre).label("grupo_nombre"),
        func.coalesce(Semestre.puntaje_maximo_asistencia, Grupo.max_asistencia).label("max_asis"),
    ).outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id)

    if grupo_id is not None:
        q = q.filter(or_(Alumno.grupo_id == grupo_id, Alumno.grupo_semestre_id == grupo_id))

    result = []
    for alumno, asistencia_total, grupo_nombre, max_asis in q.all():
        asistencia = float(asistencia_total or 0)
        max_asis_val = float(max_asis) if max_asis else MAX_ASISTENCIA_FALLBACK
        if max_asis_val == 0:
            continue
        porcentaje = round((asistencia / max_asis_val) * 100, 1)
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


def get_alumnos_en_riesgo_por_semestre(
    db: Session,
    semestre_id: int,
    umbral: float = 60.0,
    grupo_id: Optional[int] = None,
) -> list[AlumnoEnRiesgo]:
    _get_semestre_or_404(db, semestre_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    q = _get_semestre_alumnos_query(
        db,
        semestre_id,
        Alumno,
        total_asistencia_expr.label("asistencia_total"),
        GrupoSemestre.nombre.label("grupo_nombre"),
        Semestre.puntaje_maximo_asistencia.label("max_asis"),
    ).outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id)

    if grupo_id is not None:
        q = q.filter(Alumno.grupo_semestre_id == grupo_id)

    result = []
    for alumno, asistencia_total, grupo_nombre, max_asis in q.all():
        asistencia = float(asistencia_total or 0)
        max_asis_val = float(max_asis) if max_asis else MAX_ASISTENCIA_FALLBACK
        if max_asis_val == 0:
            continue
        porcentaje = round((asistencia / max_asis_val) * 100, 1)
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
# 4. Asistencia por semestre del alumno
# ---------------------------------------------------------------------------

def get_asistencia_por_semestre_alumno(db: Session, upload_id: int) -> list[AsistenciaPorSemestre]:
    upload = _get_upload_or_404(db, upload_id)

    if upload.horario_id:
        q = (
            db.query(
                Alumno.semestre,
                func.count(Alumno.id).label("total_alumnos"),
                func.avg(Alumno.total_asistencia).label("promedio"),
                func.avg(Semestre.puntaje_maximo_asistencia).label("avg_max"),
            )
            .join(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
            .join(Semestre, GrupoSemestre.semestre_id == Semestre.id)
            .filter(GrupoSemestre.horario_id == upload.horario_id, GrupoSemestre.semestre_id == upload.semestre_id, Alumno.semestre.isnot(None))
            .filter(Alumno.activo == True)
        )
    else:
        q = (
            db.query(
                Alumno.semestre,
                func.count(Alumno.id).label("total_alumnos"),
                func.avg(Alumno.total_asistencia).label("promedio"),
                func.avg(Grupo.max_asistencia).label("avg_max"),
            )
            .join(Grupo, Alumno.grupo_id == Grupo.id)
            .filter(Grupo.upload_id == upload_id, Alumno.semestre.isnot(None))
            .filter(Alumno.activo == True)
        )

    rows = q.group_by(Alumno.semestre).order_by(Alumno.semestre).all()

    result = []
    for row in rows:
        promedio = round(float(row.promedio or 0), 1)
        max_asis = float(row.avg_max) if row.avg_max else MAX_ASISTENCIA_FALLBACK
        result.append(AsistenciaPorSemestre(
            semestre=row.semestre,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            promedio_porcentaje=round((promedio / max_asis) * 100, 1) if max_asis else 0.0,
        ))
    return result


def get_asistencia_por_semestre_alumno_por_semestre(db: Session, semestre_id: int) -> list[AsistenciaPorSemestre]:
    _get_semestre_or_404(db, semestre_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    rows = (
        _get_semestre_alumnos_query(
            db,
            semestre_id,
            Alumno.semestre,
            func.count(Alumno.id).label("total_alumnos"),
            func.avg(total_asistencia_expr).label("promedio"),
            func.avg(Semestre.puntaje_maximo_asistencia).label("avg_max"),
        )
        .outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id)
        .filter(Alumno.semestre.isnot(None))
        .group_by(Alumno.semestre)
        .order_by(Alumno.semestre)
        .all()
    )

    result = []
    for row in rows:
        promedio = round(float(row.promedio or 0), 1)
        max_asis = float(row.avg_max) if row.avg_max else MAX_ASISTENCIA_FALLBACK
        result.append(AsistenciaPorSemestre(
            semestre=row.semestre,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            promedio_porcentaje=round((promedio / max_asis) * 100, 1) if max_asis else 0.0,
        ))
    return result


# ---------------------------------------------------------------------------
# 6. Ranking de grupos
# ---------------------------------------------------------------------------

def get_ranking_grupos(db: Session, upload_id: int) -> list[RankingGrupo]:
    upload = _get_upload_or_404(db, upload_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    q = _get_upload_alumnos_query(
        db,
        upload,
        func.coalesce(GrupoSemestre.id, Grupo.id).label("id"),
        func.coalesce(GrupoSemestre.nombre, Grupo.nombre).label("nombre"),
        func.coalesce(Semestre.puntaje_maximo_asistencia, Grupo.max_asistencia).label("max_asistencia"),
        func.count(Alumno.id).label("total_alumnos"),
        func.avg(total_asistencia_expr).label("promedio"),
    ).outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id).group_by(
        GrupoSemestre.id,
        GrupoSemestre.nombre,
        Semestre.puntaje_maximo_asistencia,
        Grupo.id,
        Grupo.nombre,
        Grupo.max_asistencia,
    )

    rows = q.order_by(func.avg(total_asistencia_expr).desc()).all()

    result = []
    for pos, row in enumerate(rows, start=1):
        promedio = round(float(row.promedio or 0), 1)
        max_asis = float(row.max_asistencia) if row.max_asistencia else MAX_ASISTENCIA_FALLBACK
        result.append(RankingGrupo(
            grupo_id=row.id,
            grupo=row.nombre,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            porcentaje=round((promedio / max_asis) * 100, 1) if max_asis else 0.0,
            posicion=pos,
        ))
    return result


def get_ranking_grupos_por_semestre(db: Session, semestre_id: int) -> list[RankingGrupo]:
    _get_semestre_or_404(db, semestre_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    rows = (
        _get_semestre_alumnos_query(
            db,
            semestre_id,
            GrupoSemestre.id.label("id"),
            GrupoSemestre.nombre.label("nombre"),
            Semestre.puntaje_maximo_asistencia.label("max_asistencia"),
            func.count(Alumno.id).label("total_alumnos"),
            func.avg(total_asistencia_expr).label("promedio"),
        )
        .outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id)
        .group_by(GrupoSemestre.id, GrupoSemestre.nombre, Semestre.puntaje_maximo_asistencia)
        .order_by(func.avg(total_asistencia_expr).desc())
        .all()
    )

    result = []
    for pos, row in enumerate(rows, start=1):
        promedio = round(float(row.promedio or 0), 1)
        max_asis = float(row.max_asistencia) if row.max_asistencia else MAX_ASISTENCIA_FALLBACK
        result.append(RankingGrupo(
            grupo_id=row.id,
            grupo=row.nombre,
            total_alumnos=row.total_alumnos,
            promedio_asistencia=promedio,
            porcentaje=round((promedio / max_asis) * 100, 1) if max_asis else 0.0,
            posicion=pos,
        ))
    return result


def get_resumen_semestre(db: Session, semestre_id: int) -> SemestreResumen:
    semestre = _get_semestre_or_404(db, semestre_id)
    asistencia_totals = _get_asistencia_totals_subquery(db)
    total_asistencia_expr = func.coalesce(Alumno.total_asistencia, asistencia_totals.c.total_asistencia_calculada, 0)

    agregado = (
        _get_semestre_alumnos_query(
            db,
            semestre_id,
            func.count(Alumno.id).label("total_alumnos"),
            func.avg(total_asistencia_expr).label("promedio_asistencia"),
        )
        .outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id)
        .one()
    )

    total_alumnos = int(agregado.total_alumnos or 0)
    promedio_asistencia = float(agregado.promedio_asistencia or 0)
    max_asis = float(semestre.puntaje_maximo_asistencia or MAX_ASISTENCIA_FALLBACK)

    horarios_rows = (
        db.query(Horario.id, Horario.nombre)
        .filter(Horario.semestre_id == semestre_id)
        .order_by(Horario.nombre)
        .all()
    )

    horarios = []
    for horario_id, horario_nombre in horarios_rows:
        horario_agregado = (
            _get_semestre_alumnos_query(
                db,
                semestre_id,
                func.count(Alumno.id).label("total_alumnos"),
                func.avg(total_asistencia_expr).label("promedio_asistencia"),
            )
            .outerjoin(asistencia_totals, asistencia_totals.c.alumno_id == Alumno.id)
            .filter(GrupoSemestre.horario_id == horario_id)
            .one()
        )
        ultima_fecha_real, _ = get_horario_registro_real(db, semestre_id, horario_id)

        promedio_horario = float(horario_agregado.promedio_asistencia or 0)
        horarios.append(HorarioResumenSemestre(
            horario_id=horario_id,
            nombre=horario_nombre,
            ultima_fecha_subida=ultima_fecha_real,
            total_alumnos=int(horario_agregado.total_alumnos or 0),
            porcentaje_asistencia=round((promedio_horario / max_asis) * 100, 1) if max_asis else 0.0,
        ))

    total_grupos = (
        db.query(func.count(GrupoSemestre.id))
        .filter(GrupoSemestre.semestre_id == semestre_id)
        .scalar()
        or 0
    )

    return SemestreResumen(
        semestre_id=semestre_id,
        total_alumnos=total_alumnos,
        total_grupos=int(total_grupos),
        porcentaje_asistencia_promedio=round((promedio_asistencia / max_asis) * 100, 1) if max_asis else 0.0,
        alumnos_en_riesgo=len(get_alumnos_en_riesgo_por_semestre(db, semestre_id)),
        horarios=horarios,
    )
