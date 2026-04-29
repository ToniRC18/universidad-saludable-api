#!/usr/bin/env python3
"""
Pipeline completo de finalización de semestre:
  1. Exportar datos de BD a CSV
  2. Regenerar dataset
  3. Re-entrenar modelo
  4. Reemplazar artefactos .pkl en app/ml/
  5. Señalizar recarga del modelo

Uso:
    python3 scripts/finalizar_semestre.py --semestre_id 2
    python3 scripts/finalizar_semestre.py --semestre_id 2 --dry-run
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.db.session import SessionLocal
from app.models.semestres import Semestre


BASE = Path(__file__).resolve().parent.parent
CODE = Path.home() / "Code"
ML_DIR = BASE / "app" / "ml"
RELOAD_FLAG = ML_DIR / ".reload_flag"
STATUS_FILE = ML_DIR / ".finalizacion_status.json"
ARTEFACTOS_ML = (
    "modelo_riesgo.pkl",
    "encoder_carrera.pkl",
    "imputer.pkl",
    "metadata.json",
)


def _write_status(semestre_id: int, status: str, step: str, message: str | None = None) -> None:
    ML_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "semestre_id": semestre_id,
        "status": status,
        "step": step,
        "message": message,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if STATUS_FILE.exists():
        try:
            previous = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
        if "started_at" in previous:
            payload["started_at"] = previous["started_at"]
        elif status == "processing":
            payload["started_at"] = payload["updated_at"]
    elif status == "processing":
        payload["started_at"] = payload["updated_at"]

    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_step(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout.strip())
        if exc.stderr:
            print(exc.stderr.strip())
        raise

    if result.stdout:
        print(result.stdout.strip())
    return result.stdout


def _count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def _set_semestre_estado(semestre_id: int, *, activo: bool, finalizando: bool) -> None:
    db = SessionLocal()
    try:
        semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
        if semestre is None:
            raise RuntimeError(f"Semestre {semestre_id} no encontrado para actualizar estado.")

        semestre.activo = activo
        semestre.finalizando = finalizando
        db.commit()
    finally:
        db.close()


def _get_semestre_nombre(semestre_id: int) -> str:
    db = SessionLocal()
    try:
        semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
        if semestre is None:
            raise RuntimeError(f"Semestre {semestre_id} no encontrado para obtener nombre.")
        return semestre.nombre
    finally:
        db.close()


def _normalizar_semestre_label(nombre: str) -> str:
    parts = str(nombre).strip().split()
    if len(parts) < 3:
        return nombre

    month_map = {
        "enero": "Ene",
        "febrero": "Feb",
        "marzo": "Mar",
        "abril": "Abr",
        "mayo": "May",
        "junio": "Jun",
        "julio": "Jul",
        "agosto": "Ago",
        "septiembre": "Sep",
        "octubre": "Oct",
        "noviembre": "Nov",
        "diciembre": "Dic",
    }

    inicio = month_map.get(parts[0].lower())
    fin = month_map.get(parts[1].lower())
    year = parts[2]
    if inicio and fin and year.isdigit():
        return f"{inicio}-{fin} {year}"

    return nombre


def paso1_exportar(semestre_id: int) -> int:
    print("📤 Exportando datos de BD...")
    stdout = _run_step(
        [
            sys.executable,
            str(BASE / "scripts" / "exportar_semestre.py"),
            "--semestre_id",
            str(semestre_id),
        ]
    )
    match = re.search(r"OK \((\d+) alumnos exportados\)", stdout)
    total = int(match.group(1)) if match else 0
    print(f"📤 Exportando datos de BD... OK ({total} alumnos exportados)")
    return total


def paso2_generar_dataset() -> int:
    print("📊 Generando dataset...")
    _run_step(
        [
            sys.executable,
            str(CODE / "generar_dataset.py"),
            "--input",
            str(CODE / "limpios"),
            "--output",
            str(CODE / "dataset"),
        ]
    )
    total = _count_csv_rows(CODE / "dataset" / "dataset_modelo.csv")
    print(f"📊 Generando dataset... OK (dataset_modelo.csv: {total} registros)")
    return total


def paso3_entrenar(semestre_actual: str) -> tuple[str, str]:
    print("🤖 Entrenando modelo...")
    stdout = _run_step(
        [
            sys.executable,
            str(CODE / "entrenar_modelo.py"),
            "--dataset",
            str(CODE / "dataset" / "dataset_modelo.csv"),
            "--output",
            str(CODE / "modelo"),
            "--semestre-actual",
            semestre_actual,
        ]
    )
    match = re.search(r"Mejor modelo:\s*(.+?)\s*\(F1=(\d+\.\d+)\)", stdout)
    modelo = match.group(1) if match else "Modelo no identificado"
    f1 = match.group(2) if match else "N/D"
    print(f"🤖 Entrenando modelo... OK ({modelo}, F1={f1})")
    return modelo, f1


def paso4_reemplazar_artefactos() -> None:
    print("📦 Actualizando artefactos...")
    tmp_dir = ML_DIR / "tmp_nuevo"
    backup_dir = ML_DIR / "tmp_backup"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    shutil.rmtree(backup_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for archivo in ARTEFACTOS_ML:
            src = CODE / "modelo" / archivo
            if not src.exists():
                raise FileNotFoundError(f"No se encontró artefacto requerido: {archivo}")
            if src.stat().st_size <= 0:
                raise ValueError(f"Artefacto vacío en origen: {archivo}")

            shutil.copy2(src, tmp_dir / archivo)

        for archivo in ARTEFACTOS_ML:
            staged = tmp_dir / archivo
            if not staged.exists() or staged.stat().st_size <= 0:
                raise ValueError(f"Artefacto inválido en staging: {archivo}")

        backup_dir.mkdir(parents=True, exist_ok=True)
        for archivo in ARTEFACTOS_ML:
            actual = ML_DIR / archivo
            if actual.exists():
                shutil.copy2(actual, backup_dir / archivo)

        for archivo in ARTEFACTOS_ML:
            os.replace(tmp_dir / archivo, ML_DIR / archivo)
            print(f"  ✅ {archivo}")

        for archivo in ARTEFACTOS_ML:
            final = ML_DIR / archivo
            if not final.exists() or final.stat().st_size <= 0:
                raise ValueError(f"Artefacto inválido después del swap: {archivo}")
    except Exception as exc:
        for archivo in ARTEFACTOS_ML:
            backup = backup_dir / archivo
            final = ML_DIR / archivo
            if backup.exists():
                os.replace(backup, final)
            elif final.exists():
                final.unlink()

        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise RuntimeError(f"Swap atómico de artefactos falló: {exc}") from exc

    shutil.rmtree(tmp_dir, ignore_errors=True)
    shutil.rmtree(backup_dir, ignore_errors=True)

    print("📦 Actualizando artefactos... OK")


def paso5_senalizar_recarga() -> None:
    RELOAD_FLAG.write_text("ready", encoding="utf-8")
    print("🔄 Flag de recarga creado")


def dry_run(semestre_id: int) -> None:
    print(f"🚀 Iniciando finalización del semestre ID={semestre_id} [dry-run]")
    print(f"DRY RUN: exportaría datos a {CODE / 'limpios'}")
    print(f"DRY RUN: regeneraría dataset en {CODE / 'dataset'}")
    print(f"DRY RUN: re-entrenaría modelo en {CODE / 'modelo'}")
    print(f"DRY RUN: copiaría artefactos a {BASE / 'app' / 'ml'}")
    print(f"DRY RUN: dejaría {RELOAD_FLAG} en estado listo para recarga")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semestre_id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        dry_run(args.semestre_id)
        return

    start = time.perf_counter()
    ML_DIR.mkdir(parents=True, exist_ok=True)
    if RELOAD_FLAG.exists():
        RELOAD_FLAG.unlink()
    _write_status(args.semestre_id, "processing", "starting", "Pipeline iniciado")
    semestre_actual = _normalizar_semestre_label(_get_semestre_nombre(args.semestre_id))

    try:
        print(f"🚀 Iniciando finalización del semestre ID={args.semestre_id}")
        _write_status(args.semestre_id, "processing", "exporting", "Exportando semestre a CSV")
        paso1_exportar(args.semestre_id)

        _write_status(args.semestre_id, "processing", "building_dataset", "Regenerando dataset")
        paso2_generar_dataset()

        _write_status(args.semestre_id, "processing", "training_model", "Re-entrenando modelo")
        paso3_entrenar(semestre_actual)

        _write_status(args.semestre_id, "processing", "updating_artifacts", "Copiando artefactos")
        paso4_reemplazar_artefactos()

        _write_status(args.semestre_id, "processing", "waiting_reload", "Artefactos listos para recarga")
        paso5_senalizar_recarga()
        _set_semestre_estado(args.semestre_id, activo=False, finalizando=False)

        elapsed = round(time.perf_counter() - start)
        print(f"✅ Proceso completado en {elapsed}s")
    except Exception as exc:
        if RELOAD_FLAG.exists():
            RELOAD_FLAG.unlink()
        _set_semestre_estado(args.semestre_id, activo=True, finalizando=False)
        _write_status(args.semestre_id, "idle", "failed", str(exc))
        print(f"❌ Error en la finalización del semestre: {exc}")
        raise


if __name__ == "__main__":
    main()
