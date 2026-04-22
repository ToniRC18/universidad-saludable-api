from sqlalchemy.orm import Session
from sqlalchemy import exc
from fastapi import HTTPException
from collections import defaultdict

from app.models.semestres import Carrera, Semestre, Horario, GrupoSemestre, UploadsHorario
from app.models import Alumno
from app.schemas.semestres import (
    CarreraCreate,
    CarreraUpdate,
    SemestreCreate,
    SemestreUpdate,
    HorarioCreate,
    GrupoSemestreBase,
    GrupoSemestreUpdate,
    HorarioConGrupos,
    GrupoSemestreOut
)

# --- Carreras ---

def list_carreras_agrupadas(db: Session):
    carreras = db.query(Carrera).filter(Carrera.activa == True).all()
    grouped = defaultdict(list)
    for c in carreras:
        grouped[c.facultad].append(c)
    return grouped

def list_carreras_planas(db: Session):
    return db.query(Carrera).filter(Carrera.activa == True).all()

def create_carrera(db: Session, carrera: CarreraCreate):
    db_carrera = Carrera(**carrera.model_dump())
    db.add(db_carrera)
    try:
        db.commit()
        db.refresh(db_carrera)
        return db_carrera
    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una carrera con ese nombre.")

def update_carrera(db: Session, carrera_id: int, updates: CarreraUpdate):
    db_carrera = db.query(Carrera).filter(Carrera.id == carrera_id).first()
    if not db_carrera:
        raise HTTPException(status_code=404, detail="Carrera no encontrada.")
    update_data = updates.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in update_data.items():
        setattr(db_carrera, key, value)
    try:
        db.commit()
        db.refresh(db_carrera)
        return db_carrera
    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una carrera con ese nombre.")


# --- Semestres ---

def create_semestre(db: Session, semestre: SemestreCreate):
    db_semestre = Semestre(**semestre.model_dump())
    db.add(db_semestre)
    db.commit()
    db.refresh(db_semestre)
    return db_semestre

def list_semestres(db: Session, activo: bool | None = None):
    query = db.query(Semestre)
    if activo is not None:
        query = query.filter(Semestre.activo == activo)
    return query.order_by(Semestre.created_at.desc()).all()

def get_semestre(db: Session, semestre_id: int):
    # Usado para detalle
    db_semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
    if not db_semestre:
        raise HTTPException(status_code=404, detail="Semestre no encontrado.")
    return db_semestre

def update_semestre(db: Session, semestre_id: int, updates: SemestreUpdate):
    db_semestre = get_semestre(db, semestre_id)
    # Excluimos unset para PATCH y none para evitar pisar campos not null como nombre
    update_data = updates.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in update_data.items():
        setattr(db_semestre, key, value)
    db.commit()
    db.refresh(db_semestre)
    return db_semestre


# --- Horarios ---

def create_horario(db: Session, semestre_id: int, horario: HorarioCreate):
    db_semestre = get_semestre(db, semestre_id)
    db_horario = Horario(**horario.model_dump(), semestre_id=db_semestre.id)
    db.add(db_horario)
    db.commit()
    db.refresh(db_horario)
    return db_horario

def list_horarios(db: Session, semestre_id: int):
    # Valida existencia
    get_semestre(db, semestre_id)
    return db.query(Horario).filter(Horario.semestre_id == semestre_id).all()

def eliminar_horario(db: Session, semestre_id: int, horario_id: int):
    # Verificar existencia y pertenencia
    db_horario = db.query(Horario).filter(
        Horario.id == horario_id, 
        Horario.semestre_id == semestre_id
    ).first()
    if not db_horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado en este semestre.")
    
    # Verificar si tiene uploads asociados
    has_uploads = db.query(UploadsHorario).filter(
        UploadsHorario.horario_id == horario_id,
        UploadsHorario.semestre_id == semestre_id
    ).first() is not None
    
    if has_uploads:
        raise HTTPException(
            status_code=400, 
            detail="No se puede eliminar un horario con datos de asistencia registrados."
        )
    
    db.delete(db_horario)
    db.commit()
    return True


# --- Grupos ---

def create_grupo(db: Session, semestre_id: int, grupo: GrupoSemestreBase):
    db_semestre = get_semestre(db, semestre_id)
    if grupo.horario_id:
        h = db.query(Horario).filter(Horario.id == grupo.horario_id, Horario.semestre_id == semestre_id).first()
        if not h:
            raise HTTPException(status_code=400, detail="Horario inválido o no pertenece a este semestre.")
    db_grupo = GrupoSemestre(**grupo.model_dump(), semestre_id=db_semestre.id)
    db.add(db_grupo)
    db.commit()
    db.refresh(db_grupo)
    return db_grupo

def update_grupo(db: Session, semestre_id: int, grupo_id: int, updates: GrupoSemestreUpdate):
    get_semestre(db, semestre_id)
    db_grupo = db.query(GrupoSemestre).filter(GrupoSemestre.id == grupo_id, GrupoSemestre.semestre_id == semestre_id).first()
    if not db_grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado en este semestre.")

    update_data = updates.model_dump(exclude_unset=True, exclude_none=True)
    if "horario_id" in update_data and update_data["horario_id"] is not None:
        h = db.query(Horario).filter(Horario.id == update_data["horario_id"], Horario.semestre_id == semestre_id).first()
        if not h:
            raise HTTPException(status_code=400, detail="Horario inválido o no pertenece a este semestre.")

    for key, value in update_data.items():
        setattr(db_grupo, key, value)
    db.commit()
    db.refresh(db_grupo)
    return db_grupo

def eliminar_grupo(db: Session, semestre_id: int, grupo_id: int):
    get_semestre(db, semestre_id)
    db_grupo = db.query(GrupoSemestre).filter(
        GrupoSemestre.id == grupo_id, 
        GrupoSemestre.semestre_id == semestre_id
    ).first()
    if not db_grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado en este semestre.")
    
    # Verificar si tiene alumnos asociados para seguridad
    has_alumnos = db.query(Alumno).filter(Alumno.grupo_semestre_id == grupo_id).first() is not None
    if has_alumnos:
        raise HTTPException(
            status_code=400, 
            detail="No se puede eliminar un grupo que ya tiene alumnos/asistencias cargadas."
        )
    
    db.delete(db_grupo)
    db.commit()
    return True

def desvincular_grupo(db: Session, semestre_id: int, grupo_id: int):
    get_semestre(db, semestre_id)
    db_grupo = db.query(GrupoSemestre).filter(
        GrupoSemestre.id == grupo_id, 
        GrupoSemestre.semestre_id == semestre_id
    ).first()
    if not db_grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado en este semestre.")
    
    db_grupo.horario_id = None
    db_grupo.sub_bloque = None
    db.commit()
    db.refresh(db_grupo)
    return db_grupo

def list_grupos_agrupados_por_horario(db: Session, semestre_id: int):
    get_semestre(db, semestre_id)
    # Get all horarios
    horarios = db.query(Horario).filter(Horario.semestre_id == semestre_id).all()
    # Get all grupos
    grupos = db.query(GrupoSemestre).filter(GrupoSemestre.semestre_id == semestre_id).all()

    # Map groups by horario_id
    grupos_por_horario = defaultdict(list)
    for g in grupos:
        out = GrupoSemestreOut.model_validate(g)
        if g.horario_id is None:
            grupos_por_horario[None].append(out)
        else:
            grupos_por_horario[g.horario_id].append(out)

    result = []
    for h in horarios:
        result.append(HorarioConGrupos(
            horario_id=h.id,
            horario_nombre=h.nombre,
            grupos=grupos_por_horario.get(h.id, [])
        ))

    # Add sin horario at the end if there are any
    if None in grupos_por_horario:
        result.append(HorarioConGrupos(
            horario_id=None,
            horario_nombre="Sin horario asignado",
            grupos=grupos_por_horario[None]
        ))

    return result
