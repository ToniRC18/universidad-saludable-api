from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.pruebas import (
    PeriodoSeguimiento,
    PruebaFisica,
    ResultadoPrueba,
    Seguimiento,
    SeguimientoGrupo,
)
from app.schemas.pruebas import (
    ComparacionPruebaItem,
    ComparacionSeguimientos,
    EstadisticasGrupo,
    EstadisticasPeriodo,
    EstadisticasPrueba,
    GrupoOut,
    HistoricoPrueba,
    HistoricoSemestre,
    InfoSeguimiento,
    MejoraInfo,
    PeriodoOut,
    ProgresoAlumno,
    ProgresoXPrueba,
    PruebaOut,
    RankingMejoraItem,
    SeguimientoDetalle,
    SeguimientoListItem,
    SemestresConPeriodos,
    ValorPeriodo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_404(db: Session, model, pk: int, label: str):
    obj = db.query(model).filter(model.id == pk).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{label} {pk} no encontrado.")
    return obj


def _r(v) -> Optional[float]:
    return round(float(v), 1) if v is not None else None


# ---------------------------------------------------------------------------
# Seguimientos
# ---------------------------------------------------------------------------

def crear_seguimiento(db: Session, nombre: str, descripcion: Optional[str], aplica_a_todos: bool) -> Seguimiento:
    seg = Seguimiento(nombre=nombre, descripcion=descripcion, aplica_a_todos=aplica_a_todos)
    db.add(seg)
    db.commit()
    db.refresh(seg)
    return seg


def listar_seguimientos(db: Session) -> list[SeguimientoListItem]:
    seguimientos = db.query(Seguimiento).order_by(Seguimiento.id).all()
    result = []
    for s in seguimientos:
        total_grupos = db.query(func.count(SeguimientoGrupo.id)).filter(
            SeguimientoGrupo.seguimiento_id == s.id
        ).scalar() or 0
        total_pruebas = db.query(func.count(PruebaFisica.id)).filter(
            PruebaFisica.seguimiento_id == s.id
        ).scalar() or 0
        result.append(SeguimientoListItem(
            id=s.id,
            nombre=s.nombre,
            activo=s.activo,
            aplica_a_todos=s.aplica_a_todos,
            total_grupos=total_grupos,
            total_pruebas=total_pruebas,
        ))
    return result


def detalle_seguimiento(db: Session, seguimiento_id: int) -> SeguimientoDetalle:
    s = _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    return SeguimientoDetalle(
        id=s.id,
        nombre=s.nombre,
        descripcion=s.descripcion,
        aplica_a_todos=s.aplica_a_todos,
        activo=s.activo,
        created_at=s.created_at,
        grupos=[GrupoOut.model_validate(g) for g in s.grupos],
        pruebas=[PruebaOut.model_validate(p) for p in s.pruebas],
    )


def actualizar_seguimiento(
    db: Session, seguimiento_id: int, nombre: Optional[str], descripcion: Optional[str], activo: Optional[bool]
) -> Seguimiento:
    s = _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    if nombre is not None:
        s.nombre = nombre
    if descripcion is not None:
        s.descripcion = descripcion
    if activo is not None:
        s.activo = activo
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Grupos del seguimiento
# ---------------------------------------------------------------------------

def agregar_grupo(
    db: Session,
    seguimiento_id: int,
    nombre_grupo: str,
    descripcion: Optional[str],
    upload_grupo_ref_id: Optional[int] = None,
) -> SeguimientoGrupo:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    g = SeguimientoGrupo(
        seguimiento_id=seguimiento_id,
        nombre_grupo=nombre_grupo,
        descripcion=descripcion,
        upload_grupo_ref_id=upload_grupo_ref_id,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def eliminar_grupo(db: Session, seguimiento_id: int, grupo_id: int) -> None:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    g = db.query(SeguimientoGrupo).filter(
        SeguimientoGrupo.id == grupo_id,
        SeguimientoGrupo.seguimiento_id == seguimiento_id,
    ).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Grupo {grupo_id} no encontrado en el seguimiento.")
    db.delete(g)
    db.commit()


# ---------------------------------------------------------------------------
# Pruebas del seguimiento
# ---------------------------------------------------------------------------

def agregar_prueba(
    db: Session, seguimiento_id: int, nombre: str, unidad: Optional[str], mayor_es_mejor: bool
) -> PruebaFisica:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    p = PruebaFisica(seguimiento_id=seguimiento_id, nombre=nombre, unidad=unidad, mayor_es_mejor=mayor_es_mejor)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def eliminar_prueba(db: Session, seguimiento_id: int, prueba_id: int) -> None:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    p = db.query(PruebaFisica).filter(
        PruebaFisica.id == prueba_id,
        PruebaFisica.seguimiento_id == seguimiento_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Prueba {prueba_id} no encontrada en el seguimiento.")
    db.delete(p)
    db.commit()


# ---------------------------------------------------------------------------
# Periodos
# ---------------------------------------------------------------------------

def crear_periodo(
    db: Session, seguimiento_id: int, semestre_label: str, nombre_periodo: str, fecha
) -> PeriodoSeguimiento:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    p = PeriodoSeguimiento(
        seguimiento_id=seguimiento_id,
        semestre_label=semestre_label,
        nombre_periodo=nombre_periodo,
        fecha=fecha,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def listar_periodos(db: Session, seguimiento_id: int) -> list[SemestresConPeriodos]:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")
    periodos = (
        db.query(PeriodoSeguimiento)
        .filter(PeriodoSeguimiento.seguimiento_id == seguimiento_id)
        .order_by(PeriodoSeguimiento.semestre_label, PeriodoSeguimiento.fecha)
        .all()
    )
    agrupados: dict[str, list] = {}
    for p in periodos:
        agrupados.setdefault(p.semestre_label, []).append(PeriodoOut.model_validate(p))

    return [
        SemestresConPeriodos(semestre_label=sl, periodos=ps)
        for sl, ps in agrupados.items()
    ]


# ---------------------------------------------------------------------------
# Análisis — Progreso por alumno
# ---------------------------------------------------------------------------

def get_progreso(
    db: Session,
    seguimiento_id: int,
    semestre_label: str,
    grupo_id: Optional[int] = None,
) -> list[ProgresoAlumno]:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")

    periodos = (
        db.query(PeriodoSeguimiento)
        .filter(
            PeriodoSeguimiento.seguimiento_id == seguimiento_id,
            PeriodoSeguimiento.semestre_label == semestre_label,
        )
        .order_by(PeriodoSeguimiento.fecha)
        .all()
    )
    if not periodos:
        return []

    periodo_ids = [p.id for p in periodos]
    periodos_map = {p.id: p for p in periodos}

    pruebas = (
        db.query(PruebaFisica)
        .filter(PruebaFisica.seguimiento_id == seguimiento_id)
        .order_by(PruebaFisica.id)
        .all()
    )

    query = db.query(ResultadoPrueba).filter(ResultadoPrueba.periodo_id.in_(periodo_ids))
    if grupo_id is not None:
        query = query.filter(ResultadoPrueba.grupo_id == grupo_id)

    resultados = query.all()

    # Construir estructura: {matricula: {prueba_id: {periodo_id: valor}}}
    data: dict[str, dict] = {}
    nombres: dict[str, str] = {}
    grupos_nombre: dict[str, str] = {}

    for r in resultados:
        data.setdefault(r.matricula, {}).setdefault(r.prueba_id, {})[r.periodo_id] = (
            float(r.valor) if r.valor is not None else None
        )
        if r.nombre_alumno:
            nombres[r.matricula] = r.nombre_alumno
        if r.grupo_id:
            grupo_obj = db.query(SeguimientoGrupo).filter(SeguimientoGrupo.id == r.grupo_id).first()
            if grupo_obj:
                grupos_nombre[r.matricula] = grupo_obj.nombre_grupo

    result: list[ProgresoAlumno] = []
    for matricula, pruebas_data in sorted(data.items()):
        pruebas_out: list[ProgresoXPrueba] = []
        for prueba in pruebas:
            periodos_vals = pruebas_data.get(prueba.id, {})
            # ordenar por fecha
            valores_ordenados = [
                ValorPeriodo(
                    periodo_id=p.id,
                    nombre_periodo=p.nombre_periodo,
                    valor=periodos_vals.get(p.id),
                )
                for p in periodos
            ]
            # diferencia entre primero y último con valor
            valores_con_dato = [v.valor for v in valores_ordenados if v.valor is not None]
            diferencia = None
            if len(valores_con_dato) >= 2:
                diferencia = round(valores_con_dato[-1] - valores_con_dato[0], 1)

            pruebas_out.append(ProgresoXPrueba(
                prueba_id=prueba.id,
                prueba=prueba.nombre,
                unidad=prueba.unidad,
                mayor_es_mejor=prueba.mayor_es_mejor,
                periodos=valores_ordenados,
                diferencia=diferencia,
            ))

        result.append(ProgresoAlumno(
            matricula=matricula,
            nombre=nombres.get(matricula),
            grupo=grupos_nombre.get(matricula),
            pruebas=pruebas_out,
        ))

    return result


# ---------------------------------------------------------------------------
# Análisis — Ranking de mejora por grupo
# ---------------------------------------------------------------------------

def get_ranking_mejora(
    db: Session,
    seguimiento_id: int,
    semestre_label: str,
) -> list[RankingMejoraItem]:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")

    periodos = (
        db.query(PeriodoSeguimiento)
        .filter(
            PeriodoSeguimiento.seguimiento_id == seguimiento_id,
            PeriodoSeguimiento.semestre_label == semestre_label,
        )
        .order_by(PeriodoSeguimiento.fecha)
        .all()
    )
    if len(periodos) < 2:
        return []

    periodo_inicial = periodos[0]
    periodo_final = periodos[-1]

    pruebas = (
        db.query(PruebaFisica)
        .filter(PruebaFisica.seguimiento_id == seguimiento_id)
        .all()
    )
    grupos = (
        db.query(SeguimientoGrupo)
        .filter(SeguimientoGrupo.seguimiento_id == seguimiento_id)
        .all()
    )

    result: list[RankingMejoraItem] = []
    for grupo in grupos:
        for prueba in pruebas:
            avg_inicial = db.query(func.avg(ResultadoPrueba.valor)).filter(
                ResultadoPrueba.periodo_id == periodo_inicial.id,
                ResultadoPrueba.prueba_id == prueba.id,
                ResultadoPrueba.grupo_id == grupo.id,
            ).scalar()

            avg_final = db.query(func.avg(ResultadoPrueba.valor)).filter(
                ResultadoPrueba.periodo_id == periodo_final.id,
                ResultadoPrueba.prueba_id == prueba.id,
                ResultadoPrueba.grupo_id == grupo.id,
            ).scalar()

            prom_inicial = _r(avg_inicial)
            prom_final = _r(avg_final)

            diferencia = None
            porcentaje = None
            if prom_inicial is not None and prom_final is not None:
                diferencia = round(prom_final - prom_inicial, 1)
                if prom_inicial != 0:
                    porcentaje = round((diferencia / abs(prom_inicial)) * 100, 1)

            result.append(RankingMejoraItem(
                grupo=grupo.nombre_grupo,
                prueba=prueba.nombre,
                unidad=prueba.unidad,
                mayor_es_mejor=prueba.mayor_es_mejor,
                promedio_inicial=prom_inicial,
                promedio_final=prom_final,
                diferencia=diferencia,
                porcentaje_mejora=porcentaje,
            ))

    # ordenar por diferencia desc (mayor mejora primero), nulls al final
    result.sort(key=lambda x: (x.diferencia is None, -(x.diferencia or 0)))
    return result


# ---------------------------------------------------------------------------
# Análisis — Estadísticas detalladas por periodo
# ---------------------------------------------------------------------------

def get_estadisticas(
    db: Session,
    seguimiento_id: int,
    semestre_label: str,
) -> list[EstadisticasPrueba]:
    """
    Para cada prueba del seguimiento devuelve, por periodo, las estadísticas
    descriptivas globales (todos los grupos) y desglosadas por grupo.
    """
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")

    periodos = (
        db.query(PeriodoSeguimiento)
        .filter(
            PeriodoSeguimiento.seguimiento_id == seguimiento_id,
            PeriodoSeguimiento.semestre_label == semestre_label,
        )
        .order_by(PeriodoSeguimiento.fecha)
        .all()
    )
    if not periodos:
        return []

    pruebas = (
        db.query(PruebaFisica)
        .filter(PruebaFisica.seguimiento_id == seguimiento_id)
        .order_by(PruebaFisica.id)
        .all()
    )
    grupos = (
        db.query(SeguimientoGrupo)
        .filter(SeguimientoGrupo.seguimiento_id == seguimiento_id)
        .all()
    )
    periodo_ids = [p.id for p in periodos]

    result: list[EstadisticasPrueba] = []

    for prueba in pruebas:
        # ── estadísticas globales (todos los grupos) ──────────────────────
        global_periodos: list[EstadisticasPeriodo] = []
        for periodo in periodos:
            stats = _stats_for(db, prueba.id, periodo.id, grupo_id=None)
            global_periodos.append(EstadisticasPeriodo(
                periodo_id=periodo.id,
                nombre_periodo=periodo.nombre_periodo,
                fecha=periodo.fecha,
                **stats,
            ))

        # ── estadísticas por grupo ────────────────────────────────────────
        grupos_out: list[EstadisticasGrupo] = []
        for grupo in grupos:
            g_periodos: list[EstadisticasPeriodo] = []
            for periodo in periodos:
                stats = _stats_for(db, prueba.id, periodo.id, grupo_id=grupo.id)
                g_periodos.append(EstadisticasPeriodo(
                    periodo_id=periodo.id,
                    nombre_periodo=periodo.nombre_periodo,
                    fecha=periodo.fecha,
                    **stats,
                ))

            # mejora: último promedio con dato − primer promedio con dato
            promedios = [p.promedio for p in g_periodos if p.promedio is not None]
            mejora_abs = mejora_pct = None
            if len(promedios) >= 2:
                mejora_abs = round(promedios[-1] - promedios[0], 2)
                if promedios[0] != 0:
                    mejora_pct = round((mejora_abs / abs(promedios[0])) * 100, 1)

            grupos_out.append(EstadisticasGrupo(
                grupo_id=grupo.id,
                grupo=grupo.nombre_grupo,
                periodos=g_periodos,
                mejora_abs=mejora_abs,
                mejora_pct=mejora_pct,
            ))

        result.append(EstadisticasPrueba(
            prueba_id=prueba.id,
            prueba=prueba.nombre,
            unidad=prueba.unidad,
            mayor_es_mejor=prueba.mayor_es_mejor,
            global_periodos=global_periodos,
            grupos=grupos_out,
        ))

    return result


def _stats_for(db: Session, prueba_id: int, periodo_id: int, grupo_id: Optional[int]) -> dict:
    """Devuelve n, promedio, mediana, desv_std, minimo, maximo para un periodo/grupo."""
    q = db.query(ResultadoPrueba).filter(
        ResultadoPrueba.prueba_id == prueba_id,
        ResultadoPrueba.periodo_id == periodo_id,
        ResultadoPrueba.valor.isnot(None),
    )
    if grupo_id is not None:
        q = q.filter(ResultadoPrueba.grupo_id == grupo_id)

    filas = q.all()
    valores = [float(r.valor) for r in filas if r.valor is not None]
    n = len(valores)

    if n == 0:
        return dict(n=0, promedio=None, mediana=None, desv_std=None, minimo=None, maximo=None)

    promedio = round(sum(valores) / n, 2)
    sorted_v = sorted(valores)
    mid = n // 2
    mediana = round(
        sorted_v[mid] if n % 2 == 1 else (sorted_v[mid - 1] + sorted_v[mid]) / 2, 2
    )
    variance = sum((v - promedio) ** 2 for v in valores) / n
    desv_std = round(variance ** 0.5, 2)

    return dict(
        n=n,
        promedio=promedio,
        mediana=mediana,
        desv_std=desv_std,
        minimo=round(min(valores), 2),
        maximo=round(max(valores), 2),
    )


# ---------------------------------------------------------------------------
# Análisis — Comparación entre dos seguimientos
# ---------------------------------------------------------------------------

def get_comparacion(
    db: Session,
    seg_a_id: int,
    seg_b_id: int,
    semestre_label: str,
    grupo_nombre: str,
) -> ComparacionSeguimientos:
    """
    Compara los resultados de dos seguimientos para el mismo grupo de alumnos
    y semestre.  Pruebas con el mismo nombre en ambos seguimientos se comparan
    directamente; el resto se incluye sin contraparte.
    """
    seg_a = _get_or_404(db, Seguimiento, seg_a_id, "Seguimiento A")
    seg_b = _get_or_404(db, Seguimiento, seg_b_id, "Seguimiento B")

    pruebas_list: list[ComparacionPruebaItem] = []

    # índice de pruebas de B por nombre (lower)
    pruebas_b_idx = {
        p.nombre.strip().lower(): p
        for p in db.query(PruebaFisica)
        .filter(PruebaFisica.seguimiento_id == seg_b_id)
        .all()
    }

    pruebas_a = (
        db.query(PruebaFisica)
        .filter(PruebaFisica.seguimiento_id == seg_a_id)
        .order_by(PruebaFisica.id)
        .all()
    )

    for prueba_a in pruebas_a:
        prueba_b = pruebas_b_idx.get(prueba_a.nombre.strip().lower())
        if prueba_b is None:
            continue  # sin contraparte — no se puede comparar

        mejora_a = _mejora_seguimiento(db, seg_a_id, prueba_a.id, semestre_label, grupo_nombre)
        mejora_b = _mejora_seguimiento(db, seg_b_id, prueba_b.id, semestre_label, grupo_nombre)

        ganador = _determinar_ganador(mejora_a, mejora_b, prueba_a.mayor_es_mejor)

        pruebas_list.append(ComparacionPruebaItem(
            prueba=prueba_a.nombre,
            unidad=prueba_a.unidad,
            mayor_es_mejor=prueba_a.mayor_es_mejor,
            resultado_a=mejora_a,
            resultado_b=mejora_b,
            ganador=ganador,
        ))

    return ComparacionSeguimientos(
        seguimiento_a=InfoSeguimiento(id=seg_a.id, nombre=seg_a.nombre),
        seguimiento_b=InfoSeguimiento(id=seg_b.id, nombre=seg_b.nombre),
        grupo=grupo_nombre,
        semestre_label=semestre_label,
        pruebas=pruebas_list,
    )


def _mejora_seguimiento(
    db: Session,
    seguimiento_id: int,
    prueba_id: int,
    semestre_label: str,
    grupo_nombre: str,
) -> MejoraInfo:
    """Calcula mejora (inicial → final) para una prueba/grupo/semestre en un seguimiento."""
    grupo = (
        db.query(SeguimientoGrupo)
        .filter(
            SeguimientoGrupo.seguimiento_id == seguimiento_id,
            SeguimientoGrupo.nombre_grupo.ilike(grupo_nombre.strip()),
        )
        .first()
    )
    grupo_id = grupo.id if grupo else None

    periodos = (
        db.query(PeriodoSeguimiento)
        .filter(
            PeriodoSeguimiento.seguimiento_id == seguimiento_id,
            PeriodoSeguimiento.semestre_label == semestre_label,
        )
        .order_by(PeriodoSeguimiento.fecha)
        .all()
    )

    if len(periodos) < 2:
        return MejoraInfo(
            n_inicial=0, n_final=0,
            promedio_inicial=None, promedio_final=None,
            mejora_abs=None, mejora_pct=None,
        )

    s_inicial = _stats_for(db, prueba_id, periodos[0].id, grupo_id)
    s_final   = _stats_for(db, prueba_id, periodos[-1].id, grupo_id)

    prom_ini = s_inicial["promedio"]
    prom_fin = s_final["promedio"]
    mejora_abs = mejora_pct = None
    if prom_ini is not None and prom_fin is not None:
        mejora_abs = round(prom_fin - prom_ini, 2)
        if prom_ini != 0:
            mejora_pct = round((mejora_abs / abs(prom_ini)) * 100, 1)

    return MejoraInfo(
        n_inicial=s_inicial["n"],
        n_final=s_final["n"],
        promedio_inicial=prom_ini,
        promedio_final=prom_fin,
        mejora_abs=mejora_abs,
        mejora_pct=mejora_pct,
    )


def _determinar_ganador(a: MejoraInfo, b: MejoraInfo, mayor_es_mejor: bool) -> Optional[str]:
    """Determina qué seguimiento produjo mejor mejora."""
    if a.mejora_pct is None and b.mejora_pct is None:
        return None
    if a.mejora_pct is None:
        return "B"
    if b.mejora_pct is None:
        return "A"

    # Si mayor_es_mejor, queremos mayor mejora_pct; si no, también (mejora_pct ya
    # se calcula como (final-inicial)/|inicial| — si menor es mejor y bajó, da negativo,
    # lo que en realidad es bueno; invertimos el signo para comparar)
    pct_a = a.mejora_pct if mayor_es_mejor else -a.mejora_pct
    pct_b = b.mejora_pct if mayor_es_mejor else -b.mejora_pct

    if abs(pct_a - pct_b) < 0.5:
        return "empate"
    return "A" if pct_a > pct_b else "B"


# ---------------------------------------------------------------------------
# Análisis — Histórico entre semestres
# ---------------------------------------------------------------------------

def get_historico(db: Session, seguimiento_id: int) -> list[HistoricoPrueba]:
    _get_or_404(db, Seguimiento, seguimiento_id, "Seguimiento")

    pruebas = (
        db.query(PruebaFisica)
        .filter(PruebaFisica.seguimiento_id == seguimiento_id)
        .order_by(PruebaFisica.id)
        .all()
    )

    # Obtener todos los semestre_labels
    semestres_rows = (
        db.query(PeriodoSeguimiento.semestre_label)
        .filter(PeriodoSeguimiento.seguimiento_id == seguimiento_id)
        .distinct()
        .order_by(PeriodoSeguimiento.semestre_label)
        .all()
    )
    semestres = [r[0] for r in semestres_rows]

    result: list[HistoricoPrueba] = []
    for prueba in pruebas:
        semestres_out: list[HistoricoSemestre] = []
        for semestre_label in semestres:
            # Periodo final = el de mayor fecha en ese semestre
            periodo_final = (
                db.query(PeriodoSeguimiento)
                .filter(
                    PeriodoSeguimiento.seguimiento_id == seguimiento_id,
                    PeriodoSeguimiento.semestre_label == semestre_label,
                )
                .order_by(PeriodoSeguimiento.fecha.desc())
                .first()
            )
            if not periodo_final:
                continue

            avg_val = db.query(func.avg(ResultadoPrueba.valor)).filter(
                ResultadoPrueba.prueba_id == prueba.id,
                ResultadoPrueba.periodo_id == periodo_final.id,
            ).scalar()

            if avg_val is None:
                continue

            semestres_out.append(HistoricoSemestre(
                semestre_label=semestre_label,
                periodo_final=periodo_final.nombre_periodo,
                promedio=round(float(avg_val), 1),
            ))

        if semestres_out:
            result.append(HistoricoPrueba(
                prueba_id=prueba.id,
                prueba=prueba.nombre,
                unidad=prueba.unidad,
                semestres=semestres_out,
            ))

    return result
