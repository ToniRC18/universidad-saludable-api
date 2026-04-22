#!/usr/bin/env python3
"""
Limpia registros de asistencia con valor=0 que corresponden a fechas
futuras vacias del template, no a faltas reales del maestro.

Un registro es "basura" si:
- valor = 0
- fecha > MAX(fecha WHERE valor > 0) para ese alumno
- si el alumno no tiene ningun valor > 0, no tocar nada

Uso:
    python3 scripts/limpiar_asistencias_vacias.py
    python3 scripts/limpiar_asistencias_vacias.py --dry-run
"""

import argparse
from collections import defaultdict
from pathlib import Path
import sys

from sqlalchemy import delete, func, select

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.session import SessionLocal
from app.models import Alumno, Asistencia
from app.models.semestres import GrupoSemestre, Horario, Semestre


def build_latest_positive_subquery():
    return (
        select(
            Asistencia.alumno_id.label("alumno_id"),
            func.max(Asistencia.fecha).label("ultima_fecha_real"),
        )
        .where(Asistencia.valor > 0)
        .group_by(Asistencia.alumno_id)
        .subquery()
    )


def build_garbage_ids_query(latest_positive):
    return (
        select(Asistencia.id)
        .join(Alumno, Asistencia.alumno_id == Alumno.id)
        .join(latest_positive, latest_positive.c.alumno_id == Asistencia.alumno_id)
        .join(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
        .join(Horario, GrupoSemestre.horario_id == Horario.id)
        .join(Semestre, GrupoSemestre.semestre_id == Semestre.id)
        .where(
            Asistencia.valor == 0,
            Asistencia.fecha > latest_positive.c.ultima_fecha_real,
        )
    )


def get_summary_rows(db):
    latest_positive = build_latest_positive_subquery()

    return (
        db.query(
            Semestre.id.label("semestre_id"),
            Semestre.nombre.label("semestre_nombre"),
            Horario.id.label("horario_id"),
            Horario.nombre.label("horario_nombre"),
            func.count(Asistencia.id).label("total_basura"),
        )
        .join(Alumno, Asistencia.alumno_id == Alumno.id)
        .join(latest_positive, latest_positive.c.alumno_id == Asistencia.alumno_id)
        .join(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
        .join(Horario, GrupoSemestre.horario_id == Horario.id)
        .join(Semestre, GrupoSemestre.semestre_id == Semestre.id)
        .filter(
            Asistencia.valor == 0,
            Asistencia.fecha > latest_positive.c.ultima_fecha_real,
        )
        .group_by(Semestre.id, Semestre.nombre, Horario.id, Horario.nombre)
        .order_by(Semestre.nombre, Horario.nombre)
        .all()
    )


def print_summary(rows):
    if not rows:
        print("No se encontraron asistencias basura del template.")
        return 0

    grouped = defaultdict(list)
    total = 0
    for row in rows:
        grouped[(row.semestre_id, row.semestre_nombre)].append(row)
        total += int(row.total_basura or 0)

    for (_, semestre_nombre), horario_rows in grouped.items():
        print(f"Semestre {semestre_nombre}:")
        for row in horario_rows:
            print(f"Horario {row.horario_nombre}: {int(row.total_basura or 0):,} registros basura encontrados")

    print(f"Total: {total:,} registros a eliminar")
    return total


def confirm() -> bool:
    answer = input("¿Confirmar eliminación? (s/n): ").strip().lower()
    return answer in {"s", "si", "sí", "y", "yes"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = get_summary_rows(db)
        total = print_summary(rows)

        if args.dry_run or total == 0:
            return

        if not confirm():
            print("Operación cancelada.")
            return

        latest_positive = build_latest_positive_subquery()
        garbage_ids = build_garbage_ids_query(latest_positive)
        result = db.execute(
            delete(Asistencia).where(Asistencia.id.in_(garbage_ids))
        )
        db.commit()
        print(f"Eliminados: {int(result.rowcount or 0):,} registros.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
