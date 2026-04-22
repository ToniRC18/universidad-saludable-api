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
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
CODE = Path.home() / "Code"
ML_DIR = BASE / "app" / "ml"
RELOAD_FLAG = ML_DIR / ".reload_flag"
STATUS_FILE = ML_DIR / ".finalizacion_status.json"


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


def paso3_entrenar() -> tuple[str, str]:
    print("🤖 Entrenando modelo...")
    stdout = _run_step(
        [
            sys.executable,
            str(CODE / "entrenar_modelo.py"),
            "--dataset",
            str(CODE / "dataset" / "dataset_modelo.csv"),
            "--output",
            str(CODE / "modelo"),
        ]
    )
    match = re.search(r"Mejor modelo:\s*(.+?)\s*\(F1=(\d+\.\d+)\)", stdout)
    modelo = match.group(1) if match else "Modelo no identificado"
    f1 = match.group(2) if match else "N/D"
    print(f"🤖 Entrenando modelo... OK ({modelo}, F1={f1})")
    return modelo, f1


def paso4_reemplazar_artefactos() -> None:
    print("📦 Actualizando artefactos...")
    ml_dir = BASE / "app" / "ml"
    missing = []

    for archivo in ["modelo_riesgo.pkl", "encoder_carrera.pkl", "imputer.pkl", "metadata.json"]:
        src = CODE / "modelo" / archivo
        dst = ml_dir / archivo
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✅ {archivo}")
        else:
            missing.append(archivo)

    if missing:
        missing_str = ", ".join(missing)
        raise FileNotFoundError(f"No se encontraron artefactos requeridos: {missing_str}")

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
    RELOAD_FLAG.write_text("processing", encoding="utf-8")
    _write_status(args.semestre_id, "processing", "starting", "Pipeline iniciado")

    try:
        print(f"🚀 Iniciando finalización del semestre ID={args.semestre_id}")
        _write_status(args.semestre_id, "processing", "exporting", "Exportando semestre a CSV")
        paso1_exportar(args.semestre_id)

        _write_status(args.semestre_id, "processing", "building_dataset", "Regenerando dataset")
        paso2_generar_dataset()

        _write_status(args.semestre_id, "processing", "training_model", "Re-entrenando modelo")
        paso3_entrenar()

        _write_status(args.semestre_id, "processing", "updating_artifacts", "Copiando artefactos")
        paso4_reemplazar_artefactos()

        _write_status(args.semestre_id, "processing", "waiting_reload", "Artefactos listos para recarga")
        paso5_senalizar_recarga()

        elapsed = round(time.perf_counter() - start)
        print(f"✅ Proceso completado en {elapsed}s")
    except Exception as exc:
        if RELOAD_FLAG.exists():
            RELOAD_FLAG.unlink()
        _write_status(args.semestre_id, "idle", "failed", str(exc))
        print(f"❌ Error en la finalización del semestre: {exc}")
        raise


if __name__ == "__main__":
    main()
