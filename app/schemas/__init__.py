from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


# ---------- Upload ----------

class UploadOut(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    semestre_label: Optional[str]

    class Config:
        from_attributes = True


class UploadSummary(UploadOut):
    grupos_found: int
    total_alumnos: int


# ---------- Grupo ----------

class GrupoOut(BaseModel):
    id: int
    upload_id: int
    nombre: str
    horario: Optional[str]
    total_alumnos: int

    class Config:
        from_attributes = True


# ---------- Alumno ----------

class AlumnoOut(BaseModel):
    id: int
    grupo_id: int
    folio: Optional[str]
    nombre: Optional[str]
    matricula: Optional[str]
    semestre: Optional[str]
    carrera: Optional[str]
    total_asistencia: Optional[Decimal]
    nutricion: Optional[Decimal]
    fisio: Optional[Decimal]
    limpieza: Optional[Decimal]
    coae: Optional[Decimal]
    taller: Optional[Decimal]
    total: Optional[Decimal]

    class Config:
        from_attributes = True


# ---------- Asistencia ----------

class AsistenciaOut(BaseModel):
    id: int
    alumno_id: int
    fecha: date
    valor: Decimal

    class Config:
        from_attributes = True


# ---------- Talleres (análisis comparativo) ----------

class TallerGrupoStats(BaseModel):
    grupo_id: int
    grupo_nombre: str
    avg_nutricion: Optional[float]
    avg_fisio: Optional[float]
    avg_limpieza: Optional[float]
    avg_coae: Optional[float]
    avg_taller: Optional[float]
