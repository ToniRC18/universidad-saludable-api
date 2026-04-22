from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.semestres import CarreraCreate, CarreraOut, CarreraPlanoOut, CarreraUpdate
from app.services import semestres_service

router = APIRouter(tags=["carreras"])

@router.get("", response_model=dict[str, list[CarreraOut]])
def list_carreras(db: Session = Depends(get_db)):
    """Lista todas las carreras activas, agrupadas por facultad."""
    return semestres_service.list_carreras_agrupadas(db)

@router.get("/plano", response_model=list[CarreraPlanoOut])
def list_carreras_plano(db: Session = Depends(get_db)):
    """Lista plana solo con id y nombre, para usar en dropdowns."""
    return semestres_service.list_carreras_planas(db)

@router.post("", response_model=CarreraOut, status_code=201)
def create_carrera(carrera: CarreraCreate, db: Session = Depends(get_db)):
    """Agrega una carrera nueva."""
    return semestres_service.create_carrera(db, carrera)

@router.patch("/{carrera_id}", response_model=CarreraOut)
def update_carrera(carrera_id: int, updates: CarreraUpdate, db: Session = Depends(get_db)):
    """Actualiza nombre, facultad o estado activa/inactiva."""
    return semestres_service.update_carrera(db, carrera_id, updates)
