from datetime import date, datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict

# --- Carreras ---

class CarreraBase(BaseModel):
    nombre: str
    facultad: str
    activa: bool = True

class CarreraCreate(BaseModel):
    nombre: str
    facultad: str

class CarreraUpdate(BaseModel):
    nombre: Optional[str] = None
    facultad: Optional[str] = None
    activa: Optional[bool] = None

class CarreraOut(CarreraBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class CarreraPlanoOut(BaseModel):
    id: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


# --- Horarios ---

class HorarioBase(BaseModel):
    nombre: str
    dia_1: str
    dia_2: Optional[str] = None
    dia_3: Optional[str] = None
    dia_4: Optional[str] = None

class HorarioCreate(HorarioBase):
    pass

class HorarioOut(HorarioBase):
    id: int
    semestre_id: int
    model_config = ConfigDict(from_attributes=True)


# --- Grupos ---

class GrupoSemestreBase(BaseModel):
    nombre: str
    tipo: str
    horario_id: Optional[int] = None
    sub_bloque: Optional[int] = None

class GrupoSemestreCreate(GrupoSemestreBase):
    pass

class GrupoSemestreUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    horario_id: Optional[int] = None
    sub_bloque: Optional[int] = None

class GrupoSemestreOut(GrupoSemestreBase):
    id: int
    semestre_id: int
    model_config = ConfigDict(from_attributes=True)


# --- Semestres ---

class SemestreBase(BaseModel):
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    total_semanas: int
    puntaje_maximo_asistencia: Decimal = Field(default=Decimal("60.0"))
    activo: bool = True

class SemestreCreate(BaseModel):
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    total_semanas: int
    puntaje_maximo_asistencia: Decimal = Field(default=Decimal("60.0"))

class SemestreUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None

class SemestreOut(SemestreBase):
    id: int
    total_sesiones: int
    valor_por_sesion: Decimal
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SemestreDetail(SemestreOut):
    horarios: list[HorarioOut] = []
    grupos: list[GrupoSemestreOut] = []


# --- Responses específicas ---

class HorarioConGrupos(BaseModel):
    horario_id: Optional[int]
    horario_nombre: Optional[str]
    grupos: list[GrupoSemestreOut]


class FinalizacionResponse(BaseModel):
    message: str
    semestre_id: int
    status: str


class FinalizacionStatus(BaseModel):
    reload_flag_exists: bool
    modelo_cargado: bool
    status: str
