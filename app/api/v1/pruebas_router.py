import logging
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.pruebas import PeriodoSeguimiento, Seguimiento, SeguimientoGrupo, PruebaFisica
from app.schemas.pruebas import (
    ComparacionSeguimientos,
    EstadisticasPrueba,
    GrupoCreate,
    GrupoOut,
    HistoricoPrueba,
    PeriodoCreate,
    PeriodoOut,
    PruebaCreate,
    PruebaOut,
    ProgresoAlumno,
    RankingMejoraItem,
    SeguimientoCreate,
    SeguimientoDetalle,
    SeguimientoListItem,
    SeguimientoUpdate,
    SemestresConPeriodos,
    UploadResultadosResumen,
)
from app.services import pruebas_service, plantilla_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pruebas", tags=["pruebas-fisicas"])

EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# Seguimientos
# ---------------------------------------------------------------------------

@router.post("/seguimientos", response_model=SeguimientoDetalle, status_code=201)
def crear_seguimiento(body: SeguimientoCreate, db: Session = Depends(get_db)):
    s = pruebas_service.crear_seguimiento(db, body.nombre, body.descripcion, body.aplica_a_todos)
    return pruebas_service.detalle_seguimiento(db, s.id)


@router.get("/seguimientos", response_model=list[SeguimientoListItem])
def listar_seguimientos(db: Session = Depends(get_db)):
    return pruebas_service.listar_seguimientos(db)


@router.get("/seguimientos/{seguimiento_id}", response_model=SeguimientoDetalle)
def detalle_seguimiento(seguimiento_id: int, db: Session = Depends(get_db)):
    return pruebas_service.detalle_seguimiento(db, seguimiento_id)


@router.patch("/seguimientos/{seguimiento_id}", response_model=SeguimientoDetalle)
def actualizar_seguimiento(seguimiento_id: int, body: SeguimientoUpdate, db: Session = Depends(get_db)):
    pruebas_service.actualizar_seguimiento(db, seguimiento_id, body.nombre, body.descripcion, body.activo)
    return pruebas_service.detalle_seguimiento(db, seguimiento_id)


# ---------------------------------------------------------------------------
# Grupos del seguimiento
# ---------------------------------------------------------------------------

@router.post("/seguimientos/{seguimiento_id}/grupos", response_model=GrupoOut, status_code=201)
def agregar_grupo(seguimiento_id: int, body: GrupoCreate, db: Session = Depends(get_db)):
    g = pruebas_service.agregar_grupo(
        db, seguimiento_id, body.nombre_grupo, body.descripcion, body.upload_grupo_ref_id
    )
    return GrupoOut.model_validate(g)


@router.delete("/seguimientos/{seguimiento_id}/grupos/{grupo_id}", status_code=204)
def eliminar_grupo(seguimiento_id: int, grupo_id: int, db: Session = Depends(get_db)):
    pruebas_service.eliminar_grupo(db, seguimiento_id, grupo_id)


# ---------------------------------------------------------------------------
# Pruebas del seguimiento
# ---------------------------------------------------------------------------

@router.post("/seguimientos/{seguimiento_id}/pruebas", response_model=PruebaOut, status_code=201)
def agregar_prueba(seguimiento_id: int, body: PruebaCreate, db: Session = Depends(get_db)):
    p = pruebas_service.agregar_prueba(db, seguimiento_id, body.nombre, body.unidad, body.mayor_es_mejor)
    return PruebaOut.model_validate(p)


@router.delete("/seguimientos/{seguimiento_id}/pruebas/{prueba_id}", status_code=204)
def eliminar_prueba(seguimiento_id: int, prueba_id: int, db: Session = Depends(get_db)):
    pruebas_service.eliminar_prueba(db, seguimiento_id, prueba_id)


# ---------------------------------------------------------------------------
# Periodos
# ---------------------------------------------------------------------------

@router.post("/seguimientos/{seguimiento_id}/periodos", response_model=PeriodoOut, status_code=201)
def crear_periodo(seguimiento_id: int, body: PeriodoCreate, db: Session = Depends(get_db)):
    p = pruebas_service.crear_periodo(db, seguimiento_id, body.semestre_label, body.nombre_periodo, body.fecha)
    return PeriodoOut.model_validate(p)


@router.get("/seguimientos/{seguimiento_id}/periodos", response_model=list[SemestresConPeriodos])
def listar_periodos(seguimiento_id: int, db: Session = Depends(get_db)):
    return pruebas_service.listar_periodos(db, seguimiento_id)


# ---------------------------------------------------------------------------
# Plantilla Excel
# ---------------------------------------------------------------------------

@router.get("/periodos/{periodo_id}/plantilla")
def descargar_plantilla(periodo_id: int, db: Session = Depends(get_db)):
    xlsx_bytes = plantilla_service.generar_plantilla(db, periodo_id)
    return Response(
        content=xlsx_bytes,
        media_type=EXCEL_CONTENT_TYPE,
        headers={"Content-Disposition": f"attachment; filename=plantilla_periodo_{periodo_id}.xlsx"},
    )


@router.post("/periodos/{periodo_id}/resultados", response_model=UploadResultadosResumen, status_code=201)
async def subir_resultados(
    periodo_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos Excel (.xlsx, .xls).")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    resumen = plantilla_service.parsear_resultados(db, periodo_id, file_bytes)
    return UploadResultadosResumen(**resumen)


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

@router.get("/seguimientos/{seguimiento_id}/progreso", response_model=list[ProgresoAlumno])
def progreso_alumnos(
    seguimiento_id: int,
    semestre_label: str = Query(...),
    grupo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return pruebas_service.get_progreso(db, seguimiento_id, semestre_label, grupo_id)


@router.get("/seguimientos/{seguimiento_id}/ranking-mejora", response_model=list[RankingMejoraItem])
def ranking_mejora(
    seguimiento_id: int,
    semestre_label: str = Query(...),
    db: Session = Depends(get_db),
):
    return pruebas_service.get_ranking_mejora(db, seguimiento_id, semestre_label)


@router.get("/seguimientos/{seguimiento_id}/historico", response_model=list[HistoricoPrueba])
def historico(seguimiento_id: int, db: Session = Depends(get_db)):
    return pruebas_service.get_historico(db, seguimiento_id)


@router.get("/seguimientos/{seguimiento_id}/estadisticas", response_model=list[EstadisticasPrueba])
def estadisticas(
    seguimiento_id: int,
    semestre_label: str = Query(...),
    db: Session = Depends(get_db),
):
    return pruebas_service.get_estadisticas(db, seguimiento_id, semestre_label)


@router.get("/comparar", response_model=ComparacionSeguimientos)
def comparar_seguimientos(
    seg_a: int = Query(..., description="ID del primer seguimiento"),
    seg_b: int = Query(..., description="ID del segundo seguimiento"),
    semestre_label: str = Query(...),
    grupo_nombre: str = Query(...),
    db: Session = Depends(get_db),
):
    return pruebas_service.get_comparacion(db, seg_a, seg_b, semestre_label, grupo_nombre)
