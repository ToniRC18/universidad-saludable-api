from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator, AliasPath


# ---------- Upload ----------

class UploadOut(BaseModel):
    id: int = Field(..., serialization_alias="upload_id")
    filename: str
    uploaded_at: datetime
    semestre_label: Optional[str] = None
    semestre_id: Optional[int] = None
    horario_id: Optional[int] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class UploadSummary(UploadOut):
    grupos_found: int
    total_alumnos: int


class AlumnoResumen(BaseModel):
    matricula: str
    nombre: str


class UploadUpsertResponse(BaseModel):
    upload_id: int
    semestre_id: int
    semestre_nombre: str
    horario_id: int
    horario_nombre: str
    actualizado: bool
    ultima_fecha_subida: Optional[date]
    hojas_procesadas: int
    hojas_saltadas: int
    total_alumnos: int
    asistencias_nuevas: int
    asistencias_protegidas: int
    alumnos_nuevos: list[AlumnoResumen] = []
    alumnos_no_encontrados: list[AlumnoResumen] = []
    warning: Optional[str] = None


class EstadoHorarioOut(BaseModel):
    horario_id: int
    nombre: str
    semestre_id: int
    ultima_fecha_subida: Optional[date]
    total_alumnos: int
    total_grupos: int
    semanas_registradas: int
    semanas_totales: int
    porcentaje_completitud: float


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

class AlumnoUpdate(BaseModel):
    activo: Optional[bool] = None

class AlumnoOut(BaseModel):
    id: int
    grupo_id: Optional[int] = None # Alumno might not have a group in new model
    grupo_semestre_id: Optional[int] = None
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
    # 'total' en BD = suma de talleres (máx 40 pts), se expone como total_talleres
    total_talleres: Optional[Decimal] = Field(None, validation_alias="total")
    porcentaje_asistencia: Optional[float] = None
    porcentaje_talleres: Optional[float] = None
    activo: bool
    
    # Campos auxiliares para el cálculo (leídos desde las relaciones)
    max_asistencia_grupo: Optional[float] = Field(None, validation_alias=AliasPath("grupo", "max_asistencia"))
    max_asistencia_semestre: Optional[float] = Field(None, validation_alias=AliasPath("grupo_semestre", "semestre", "puntaje_maximo_asistencia"))

    class Config:
        from_attributes = True
        populate_by_name = True

    @model_validator(mode="after")
    def compute_porcentajes(self):
        # Jerarquía: Semestre -> Grupo -> Fallback 60
        if self.max_asistencia_semestre is not None:
            max_asis = float(self.max_asistencia_semestre)
        elif self.max_asistencia_grupo is not None:
            max_asis = float(self.max_asistencia_grupo)
        else:
            max_asis = 60.0

        if self.total_asistencia is not None:
            self.porcentaje_asistencia = round(float(self.total_asistencia) / max_asis * 100, 1) if max_asis else 0.0
            
        if self.total_talleres is not None:
            self.porcentaje_talleres = round(float(self.total_talleres) / 40 * 100, 1)
        return self


# ---------- Asistencia ----------

class AsistenciaOut(BaseModel):
    id: int
    alumno_id: int
    fecha: date
    valor: Decimal

    class Config:
        from_attributes = True
