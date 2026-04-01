from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class SeguimientoCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    aplica_a_todos: bool = False


class SeguimientoUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None


class GrupoCreate(BaseModel):
    nombre_grupo: str
    descripcion: Optional[str] = None
    upload_grupo_ref_id: Optional[int] = None


class PruebaCreate(BaseModel):
    nombre: str
    unidad: Optional[str] = None
    mayor_es_mejor: bool = True


class PeriodoCreate(BaseModel):
    semestre_label: str
    nombre_periodo: str
    fecha: date


# ---------------------------------------------------------------------------
# Responses — catálogo
# ---------------------------------------------------------------------------

class GrupoOut(BaseModel):
    id: int
    nombre_grupo: str
    descripcion: Optional[str]

    class Config:
        from_attributes = True


class PruebaOut(BaseModel):
    id: int
    nombre: str
    unidad: Optional[str]
    mayor_es_mejor: bool

    class Config:
        from_attributes = True


class PeriodoOut(BaseModel):
    id: int
    semestre_label: str
    nombre_periodo: str
    fecha: date

    class Config:
        from_attributes = True


class SeguimientoListItem(BaseModel):
    id: int
    nombre: str
    activo: bool
    aplica_a_todos: bool
    total_grupos: int
    total_pruebas: int


class SeguimientoDetalle(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    aplica_a_todos: bool
    activo: bool
    created_at: datetime
    grupos: list[GrupoOut]
    pruebas: list[PruebaOut]


class SemestresConPeriodos(BaseModel):
    semestre_label: str
    periodos: list[PeriodoOut]


# ---------------------------------------------------------------------------
# Responses — upload de resultados
# ---------------------------------------------------------------------------

class UploadResultadosResumen(BaseModel):
    total_procesadas: int
    total_guardadas: int
    total_saltadas: int


# ---------------------------------------------------------------------------
# Responses — análisis
# ---------------------------------------------------------------------------

class ValorPeriodo(BaseModel):
    periodo_id: int
    nombre_periodo: str
    valor: Optional[float]


class ProgresoXPrueba(BaseModel):
    prueba_id: int
    prueba: str
    unidad: Optional[str]
    mayor_es_mejor: bool
    periodos: list[ValorPeriodo]
    diferencia: Optional[float]  # último - primero (con valor)


class ProgresoAlumno(BaseModel):
    matricula: str
    nombre: Optional[str]
    grupo: Optional[str]
    pruebas: list[ProgresoXPrueba]


class RankingMejoraItem(BaseModel):
    grupo: str
    prueba: str
    unidad: Optional[str]
    mayor_es_mejor: bool
    promedio_inicial: Optional[float]
    promedio_final: Optional[float]
    diferencia: Optional[float]
    porcentaje_mejora: Optional[float]


class HistoricoSemestre(BaseModel):
    semestre_label: str
    periodo_final: str
    promedio: float


class HistoricoPrueba(BaseModel):
    prueba_id: int
    prueba: str
    unidad: Optional[str]
    semestres: list[HistoricoSemestre]


# ---------------------------------------------------------------------------
# Responses — estadísticas detalladas por periodo
# ---------------------------------------------------------------------------

class EstadisticasPeriodo(BaseModel):
    periodo_id: int
    nombre_periodo: str
    fecha: date
    n: int
    promedio: Optional[float]
    mediana: Optional[float]
    desv_std: Optional[float]
    minimo: Optional[float]
    maximo: Optional[float]


class EstadisticasGrupo(BaseModel):
    grupo_id: int
    grupo: str
    periodos: list[EstadisticasPeriodo]
    mejora_abs: Optional[float]   # promedio final − promedio inicial
    mejora_pct: Optional[float]   # % de mejora respecto al inicial


class EstadisticasPrueba(BaseModel):
    prueba_id: int
    prueba: str
    unidad: Optional[str]
    mayor_es_mejor: bool
    global_periodos: list[EstadisticasPeriodo]   # todos los grupos combinados
    grupos: list[EstadisticasGrupo]


# ---------------------------------------------------------------------------
# Responses — comparación entre dos seguimientos
# ---------------------------------------------------------------------------

class MejoraInfo(BaseModel):
    n_inicial: int
    n_final: int
    promedio_inicial: Optional[float]
    promedio_final: Optional[float]
    mejora_abs: Optional[float]
    mejora_pct: Optional[float]


class ComparacionPruebaItem(BaseModel):
    prueba: str
    unidad: Optional[str]
    mayor_es_mejor: bool
    resultado_a: MejoraInfo
    resultado_b: MejoraInfo
    ganador: Optional[str]   # "A", "B", "empate" o None si sin datos


class InfoSeguimiento(BaseModel):
    id: int
    nombre: str


class ComparacionSeguimientos(BaseModel):
    seguimiento_a: InfoSeguimiento
    seguimiento_b: InfoSeguimiento
    grupo: str
    semestre_label: str
    pruebas: list[ComparacionPruebaItem]
