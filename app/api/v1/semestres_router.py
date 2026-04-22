import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Response, Query, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Alumno
from app.models.semestres import GrupoSemestre, Horario
from app.schemas.semestres import (
    SemestreCreate, SemestreOut, SemestreUpdate, SemestreDetail,
    HorarioCreate, HorarioOut,
    GrupoSemestreOut, GrupoSemestreUpdate,
    HorarioConGrupos, GrupoSemestreCreate,
    FinalizacionResponse, FinalizacionStatus,
)
from app.schemas import EstadoHorarioOut
from app.services import semestres_service
from app.services import plantilla_excel_service
from app.services import prediccion_service
from app.services import stats_service

router = APIRouter(tags=["semestres"])

BASE_DIR = Path(__file__).resolve().parents[3]
FINALIZAR_SCRIPT = BASE_DIR / "scripts" / "finalizar_semestre.py"
ML_DIR = BASE_DIR / "app" / "ml"
STATUS_FILE = ML_DIR / ".finalizacion_status.json"

# --- Semestres ---

@router.post("", response_model=SemestreOut, status_code=201)
def create_semestre(semestre: SemestreCreate, db: Session = Depends(get_db)):
    """Crear un semestre nuevo."""
    return semestres_service.create_semestre(db, semestre)

@router.get("", response_model=list[SemestreOut])
def list_semestres(activo: bool | None = Query(None), db: Session = Depends(get_db)):
    """Lista todos los semestres con sus datos calculados."""
    return semestres_service.list_semestres(db, activo=activo)

@router.get("/{semestre_id}", response_model=SemestreDetail)
def get_semestre(semestre_id: int, db: Session = Depends(get_db)):
    """Detalle completo: datos del semestre + lista de horarios + lista de grupos."""
    semestre = semestres_service.get_semestre(db, semestre_id)
    horarios = semestres_service.list_horarios(db, semestre_id)
    # Get flat list of grupos for detail view
    grupos = []
    # Usaremos una agrupación si lo requiere, pero el schema SemestreDetail dice list[GrupoSemestreOut]
    horarios_con_grupos = semestres_service.list_grupos_agrupados_por_horario(db, semestre_id)
    for h_g in horarios_con_grupos:
        grupos.extend(h_g.grupos)
    
    # Creamos la representation Detail manualmente o usando mapping
    detail = SemestreDetail.model_validate(semestre)
    detail.horarios = horarios
    detail.grupos = grupos
    return detail

@router.patch("/{semestre_id}", response_model=SemestreOut)
def update_semestre(semestre_id: int, updates: SemestreUpdate, db: Session = Depends(get_db)):
    """Actualizar nombre, estado activo o flag de talleres."""
    return semestres_service.update_semestre(db, semestre_id, updates)

@router.patch("/{semestre_id}/tiene-talleres", response_model=SemestreOut)
def update_tiene_talleres(semestre_id: int, tiene_talleres: bool, db: Session = Depends(get_db)):
    """Actualizar específicamente si el semestre tiene talleres."""
    return semestres_service.update_semestre(db, semestre_id, SemestreUpdate(tiene_talleres=tiene_talleres))


@router.post("/{semestre_id}/finalizar", response_model=FinalizacionResponse, status_code=202)
def finalizar_semestre(semestre_id: int, db: Session = Depends(get_db)):
    """Marca el semestre como finalizado y dispara el pipeline ML en background."""
    semestre = semestres_service.get_semestre(db, semestre_id)
    if not semestre.activo:
        raise HTTPException(status_code=400, detail="El semestre ya está inactivo.")

    semestre.activo = False
    db.commit()
    db.refresh(semestre)

    try:
        subprocess.Popen(
            [
                sys.executable,
                str(FINALIZAR_SCRIPT),
                "--semestre_id",
                str(semestre_id),
            ],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        semestre.activo = True
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo iniciar el proceso de finalización: {exc}",
        ) from exc

    return FinalizacionResponse(
        message="Semestre marcado como finalizado. Re-entrenamiento iniciado en background.",
        semestre_id=semestre_id,
        status="processing",
    )


@router.get("/{semestre_id}/finalizacion-status", response_model=FinalizacionStatus)
def get_finalizacion_status(semestre_id: int, db: Session = Depends(get_db)):
    """Devuelve el estado del pipeline de finalización y recarga del modelo."""
    semestres_service.get_semestre(db, semestre_id)

    estado_modelo = prediccion_service.obtener_estado_modelo()
    status = "idle"

    if STATUS_FILE.exists():
        try:
            status_data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            status_data = {}

        if status_data.get("semestre_id") == semestre_id:
            status = status_data.get("status", "idle")

    if status == "idle" and estado_modelo.get("semestre_id") == semestre_id:
        status = estado_modelo.get("status", "idle")

    return FinalizacionStatus(
        reload_flag_exists=bool(estado_modelo["reload_flag_exists"]),
        modelo_cargado=bool(estado_modelo["modelo_cargado"]),
        status=status if status in {"processing", "completed"} else "idle",
    )


# --- Horarios ---

@router.post("/{semestre_id}/horarios", response_model=HorarioOut, status_code=201)
def create_horario(semestre_id: int, horario: HorarioCreate, db: Session = Depends(get_db)):
    """Agregar horario al semestre."""
    return semestres_service.create_horario(db, semestre_id, horario)

@router.get("/{semestre_id}/horarios", response_model=list[HorarioOut])
def list_horarios(semestre_id: int, db: Session = Depends(get_db)):
    """Lista horarios del semestre."""
    return semestres_service.list_horarios(db, semestre_id)

@router.delete("/{semestre_id}/horarios/{horario_id}", status_code=204)
def delete_horario(semestre_id: int, horario_id: int, db: Session = Depends(get_db)):
    """Eliminar horario y sus grupos asociados (si no hay uploads)."""
    semestres_service.eliminar_horario(db, semestre_id, horario_id)
    return Response(status_code=204)

@router.get("/{semestre_id}/horarios/{horario_id}/estado", response_model=EstadoHorarioOut)
def get_estado_horario(semestre_id: int, horario_id: int, db: Session = Depends(get_db)):
    """Devuelve el estado actual de los uploads y el avance del horario en el semestre."""
    semestre = semestres_service.get_semestre(db, semestre_id)
    horario = db.query(Horario).filter(
        Horario.id == horario_id,
        Horario.semestre_id == semestre_id,
    ).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado en este semestre.")

    ultima_fecha_real, semanas_reg = stats_service.get_horario_registro_real(db, semestre_id, horario_id)

    total_grupos = db.query(func.count(GrupoSemestre.id)).filter(
        GrupoSemestre.horario_id == horario_id,
        GrupoSemestre.semestre_id == semestre_id
    ).scalar() or 0

    total_alumnos = db.query(func.count(Alumno.id)).join(
        GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id
    ).filter(
        GrupoSemestre.horario_id == horario_id,
        GrupoSemestre.semestre_id == semestre_id,
        Alumno.activo.is_(True)
    ).scalar() or 0

    if not ultima_fecha_real:
        return EstadoHorarioOut(
            horario_id=horario_id,
            nombre=horario.nombre,
            semestre_id=semestre_id,
            ultima_fecha_subida=None,
            total_alumnos=int(total_alumnos),
            total_grupos=int(total_grupos),
            semanas_registradas=0,
            semanas_totales=semestre.total_semanas,
            porcentaje_completitud=0.0,
        )

    semanas_registradas = min(int(semanas_reg), semestre.total_semanas)

    return EstadoHorarioOut(
        horario_id=horario_id,
        nombre=horario.nombre,
        semestre_id=semestre_id,
        ultima_fecha_subida=ultima_fecha_real,
        total_alumnos=int(total_alumnos),
        total_grupos=int(total_grupos),
        semanas_registradas=semanas_registradas,
        semanas_totales=semestre.total_semanas,
        porcentaje_completitud=round(min((semanas_registradas / semestre.total_semanas) * 100, 100.0), 1) if semestre.total_semanas else 0.0
    )


# --- Grupos ---

@router.post("/{semestre_id}/grupos", response_model=GrupoSemestreOut, status_code=201)
def create_grupo(semestre_id: int, grupo: GrupoSemestreCreate, db: Session = Depends(get_db)):
    """Agregar grupo al semestre."""
    return semestres_service.create_grupo(db, semestre_id, grupo)

@router.get("/{semestre_id}/grupos", response_model=list[HorarioConGrupos])
def list_grupos(semestre_id: int, db: Session = Depends(get_db)):
    """Lista grupos del semestre, agrupados por horario."""
    return semestres_service.list_grupos_agrupados_por_horario(db, semestre_id)

@router.patch("/{semestre_id}/grupos/{grupo_id}", response_model=GrupoSemestreOut)
def update_grupo(semestre_id: int, grupo_id: int, updates: GrupoSemestreUpdate, db: Session = Depends(get_db)):
    """Actualizar nombre, tipo u horario de un grupo."""
    return semestres_service.update_grupo(db, semestre_id, grupo_id, updates)

@router.post("/{semestre_id}/grupos/{grupo_id}/desvincular", response_model=GrupoSemestreOut)
def desvincular_grupo(semestre_id: int, grupo_id: int, db: Session = Depends(get_db)):
    """Quitar el horario asignado a un grupo."""
    return semestres_service.desvincular_grupo(db, semestre_id, grupo_id)

@router.delete("/{semestre_id}/grupos/{grupo_id}", status_code=204)
def delete_grupo(semestre_id: int, grupo_id: int, db: Session = Depends(get_db)):
    """Eliminar un grupo (solo si no tiene alumnos)."""
    semestres_service.eliminar_grupo(db, semestre_id, grupo_id)
    return Response(status_code=204)

# --- Plantilla Excel ---

@router.get("/{semestre_id}/horarios/{horario_id}/plantilla")
def download_plantilla(
    semestre_id: int, 
    horario_id: int, 
    sub_bloque: Optional[int] = Query(None, ge=1, le=2),
    db: Session = Depends(get_db)
):
    """Genera y descarga un archivo .xlsx de plantilla para llenar asistencias."""
    from app.models.semestres import Horario
    
    # Validación específica de sub_bloque 2
    if sub_bloque == 2:
        horario = db.query(Horario).filter(Horario.id == horario_id).first()
        if horario and not horario.dia_3:
            raise HTTPException(status_code=400, detail="Este horario no tiene sub-bloque 2 configurado.")

    file_bytes, filename = plantilla_excel_service.generar_plantilla(db, semestre_id, horario_id, sub_bloque)
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
