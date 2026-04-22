#!/usr/bin/env python3
"""
Exporta los datos de un semestre de BD al formato CSV que espera
generar_dataset.py (~/Code/limpios/).

Uso:
    python3 scripts/exportar_semestre.py --semestre_id 2
"""

import argparse
import re
import unicodedata
from pathlib import Path

from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models import Alumno
from app.models.semestres import GrupoSemestre, Horario, Semestre


OUTPUT_DIR = Path.home() / "Code" / "limpios"


def normalizar_archivo(label: str) -> str:
    normalized = "".join(
        ch
        for ch in unicodedata.normalize("NFD", label.lower())
        if unicodedata.category(ch) != "Mn"
    )
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if not normalized.startswith("horario_"):
        normalized = f"horario_{normalized}"
    return f"{normalized}.csv"


def formatear_semestre_grado(value: str | None) -> str:
    if not value:
        return ""

    text = str(value).strip()
    match = re.search(r"\d+", text)
    if not match:
        return text

    numero = int(match.group())
    suffix_map = {
        1: "1ro",
        2: "2do",
        3: "3ro",
        4: "4to",
        5: "5to",
        6: "6to",
        7: "7mo",
        8: "8vo",
        9: "9no",
        10: "10mo",
    }
    return suffix_map.get(numero, f"{numero}to")


def format_decimal(value) -> str:
    if value is None:
        return ""

    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def exportar_semestre(semestre_id: int) -> tuple[Path, int]:
    db = SessionLocal()
    try:
        semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
        if not semestre:
            raise ValueError(f"Semestre {semestre_id} no encontrado.")

        semestre_label = getattr(semestre, "semestre_label", None) or semestre.nombre
        alumnos = (
            db.query(Alumno)
            .join(GrupoSemestre, Alumno.grupo_semestre_id == GrupoSemestre.id)
            .join(Horario, GrupoSemestre.horario_id == Horario.id)
            .options(selectinload(Alumno.asistencias))
            .filter(Horario.semestre_id == semestre_id, Alumno.activo.is_(True))
            .order_by(Horario.nombre.asc(), GrupoSemestre.nombre.asc(), Alumno.nombre.asc())
            .all()
        )

        if not alumnos:
            raise ValueError(f"No se encontraron alumnos activos para el semestre {semestre_id}.")

        fechas = sorted(
            {
                asistencia.fecha.isoformat()
                for alumno in alumnos
                for asistencia in alumno.asistencias
            }
        )

        columnas = ["Nombre", "Matricula", "Carrera", "Semestre", *fechas, "ASISTENCIA"]
        rows = []

        for alumno in alumnos:
            asistencias_por_fecha = {asistencia.fecha.isoformat(): format_decimal(asistencia.valor) for asistencia in alumno.asistencias}
            row = {
                "Nombre": alumno.nombre or "",
                "Matricula": alumno.matricula or "",
                "Carrera": alumno.carrera or "",
                "Semestre": formatear_semestre_grado(alumno.semestre),
                "ASISTENCIA": format_decimal(alumno.total_asistencia),
            }
            for fecha in fechas:
                row[fecha] = asistencias_por_fecha.get(fecha, "")
            rows.append(row)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / normalizar_archivo(semestre_label)

        import csv

        with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(rows)

        return output_path, len(rows)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--semestre_id", type=int, required=True)
    args = parser.parse_args()

    output_path, total_alumnos = exportar_semestre(args.semestre_id)
    print(f"CSV generado: {output_path}")
    print(f"OK ({total_alumnos} alumnos exportados)")


if __name__ == "__main__":
    main()
