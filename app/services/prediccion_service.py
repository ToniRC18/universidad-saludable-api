import json
import logging
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Alumno, Grupo, Prediccion, Upload
from app.models.semestres import GrupoSemestre

logger = logging.getLogger(__name__)

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
RELOAD_FLAG = ML_DIR / ".reload_flag"
STATUS_FILE = ML_DIR / ".finalizacion_status.json"

_modelo = None
_encoder = None
_imputer = None
_metadata: dict[str, Any] = {}
_modelo_cargado = False


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _leer_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {}

    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("No se pudo leer %s: %s", STATUS_FILE, exc)
        return {}


def _escribir_status(data: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _marcar_status_completado() -> None:
    data = _leer_status()
    if not data:
        return

    data["status"] = "completed"
    data["finished_at"] = _utc_now_iso()
    data["last_reload_at"] = _utc_now_iso()
    _escribir_status(data)


def _cargar_metadata() -> dict[str, Any]:
    metadata_path = ML_DIR / "metadata.json"
    if not metadata_path.exists():
        return {}

    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("No se pudo leer metadata.json: %s", exc)
        return {}


def _feature_cols() -> list[str]:
    cols = _metadata.get("features")
    if isinstance(cols, list) and cols:
        return cols

    return [f"pct_semana_{i}" for i in range(1, 14)] + [
        "pct_mitad",
        "tendencia",
        "racha_max_faltas",
        "carrera_enc",
    ]


def _week_feature_cols() -> list[str]:
    return [col for col in _feature_cols() if col.startswith("pct_semana_")]


def _contenido_flag() -> str:
    if not RELOAD_FLAG.exists():
        return ""

    try:
        return RELOAD_FLAG.read_text(encoding="utf-8").strip().lower()
    except Exception:
        return "ready"


def recargar_modelo():
    """Recarga los artefactos .pkl desde app/ml/ sin reiniciar."""
    global _modelo, _encoder, _imputer, _metadata, _modelo_cargado

    try:
        modelo = joblib.load(ML_DIR / "modelo_riesgo.pkl")
        encoder = joblib.load(ML_DIR / "encoder_carrera.pkl")
        imputer = joblib.load(ML_DIR / "imputer.pkl")
        metadata = _cargar_metadata()

        _modelo = modelo
        _encoder = encoder
        _imputer = imputer
        _metadata = metadata
        _modelo_cargado = True

        logger.info("Modelo recargado exitosamente")
        if RELOAD_FLAG.exists():
            RELOAD_FLAG.unlink()
        _marcar_status_completado()
        return True
    except Exception as exc:
        logger.error("Error recargando modelo: %s", exc)
        return False


def verificar_recarga_pendiente() -> bool:
    flag_state = _contenido_flag()
    if flag_state == "ready":
        logger.info("Flag de recarga detectado. Recargando modelo...")
        recargar_modelo()
    return _modelo_cargado


def modelo_disponible() -> bool:
    verificar_recarga_pendiente()
    return _modelo_cargado and _modelo is not None and _encoder is not None and _imputer is not None


def obtener_estado_modelo() -> dict[str, Any]:
    flag_state = _contenido_flag()
    if flag_state == "ready":
        verificar_recarga_pendiente()
        flag_state = _contenido_flag()

    status_data = _leer_status()
    status_value = "idle"
    if status_data.get("status") == "completed":
        status_value = "completed"
    elif RELOAD_FLAG.exists() or status_data.get("status") == "processing":
        status_value = "processing"

    return {
        "reload_flag_exists": RELOAD_FLAG.exists(),
        "modelo_cargado": modelo_disponible(),
        "status": status_value,
        "semestre_id": status_data.get("semestre_id"),
    }


def _racha_max_faltas(valores: list[float]) -> int:
    max_racha = 0
    racha = 0
    for valor in valores:
        if valor == 0:
            racha += 1
            max_racha = max(max_racha, racha)
        else:
            racha = 0
    return max_racha


def _calcular_tendencia(porcentajes: list[float]) -> float:
    if len(porcentajes) < 2:
        return 0.0

    y = np.array(porcentajes, dtype=float)
    if np.std(y) == 0:
        return 0.0

    x = np.arange(len(porcentajes))
    return round(float(np.polyfit(x, y, 1)[0]), 4)


def _valor_por_sesion(valores: list[float], max_asistencia: float, total_semanas: int) -> float:
    positivos = [valor for valor in valores if valor > 0]
    if positivos:
        counts: dict[float, int] = {}
        for valor in positivos:
            counts[valor] = counts.get(valor, 0) + 1
        return max(sorted(counts), key=lambda item: counts[item])

    total_sesiones = total_semanas * 2
    if total_sesiones > 0 and max_asistencia > 0:
        return max_asistencia / total_sesiones
    return 2.5


def normalizar_semestre_cursando(val) -> int:
    normalized = "".join(
        c for c in unicodedata.normalize("NFD", str(val).lower())
        if unicodedata.category(c) != "Mn"
    ).strip()
    if normalized.isdigit():
        semestre = int(normalized)
        return semestre if 1 <= semestre <= 6 else 0

    semestre_map = {
        "1 sem": 1,
        "1 semestre": 1,
        "1 er semestre": 1,
        "1er": 1,
        "1er semestre": 1,
        "primer": 1,
        "primero": 1,
        "2do": 2,
        "segundo": 2,
        "3er": 3,
        "tercero": 3,
        "4 semestre": 4,
        "4 semestre ": 4,
        "4to": 4,
        "4to semestre": 4,
        "cuarto": 4,
        "5to": 5,
        "quinto": 5,
        "6 semestre": 6,
        "6to": 6,
        "6to semestre": 6,
        "sexto": 6,
    }
    return semestre_map.get(normalized, 0)


def _build_features(alumno: Alumno) -> dict[str, float]:
    total_semanas_modelo = max(len(_week_feature_cols()), 1)
    total_semanas_semestre = getattr(alumno.grupo_semestre.semestre, "total_semanas", None) if alumno.grupo_semestre else None
    total_semanas_semestre = total_semanas_semestre or total_semanas_modelo

    max_asistencia = 60.0
    if alumno.grupo and alumno.grupo.max_asistencia is not None:
        max_asistencia = float(alumno.grupo.max_asistencia)
    elif alumno.grupo_semestre and alumno.grupo_semestre.semestre:
        max_asistencia = float(alumno.grupo_semestre.semestre.puntaje_maximo_asistencia or 60.0)

    asistencias = sorted(alumno.asistencias, key=lambda item: item.fecha)
    valores = [float(asistencia.valor) for asistencia in asistencias]

    dias_por_semana = 2
    if alumno.grupo_semestre and alumno.grupo_semestre.horario:
        horario = alumno.grupo_semestre.horario
        dias_sub_bloque_1 = [horario.dia_1, horario.dia_2]
        dias_sub_bloque_2 = [horario.dia_3, horario.dia_4]

        if alumno.grupo_semestre.sub_bloque == 1:
            dias_por_semana = sum(1 for dia in dias_sub_bloque_1 if dia)
        elif alumno.grupo_semestre.sub_bloque == 2:
            dias_por_semana = sum(1 for dia in dias_sub_bloque_2 if dia)
        else:
            dias_por_semana = sum(
                1 for dia in [horario.dia_1, horario.dia_2, horario.dia_3, horario.dia_4]
                if dia
            )

        dias_por_semana = dias_por_semana or 2

    sesiones_esperadas = total_semanas_semestre * dias_por_semana
    sesiones_faltantes = max(sesiones_esperadas - len(valores), 0)
    if sesiones_faltantes >= dias_por_semana:
        logger.warning(
            "Serie de asistencias incompleta para matricula=%s: %s sesiones faltantes (esperadas=%s, reales=%s)",
            alumno.matricula,
            sesiones_faltantes,
            sesiones_esperadas,
            len(valores),
        )

    valor_sesion = _valor_por_sesion(valores, max_asistencia, total_semanas_semestre)
    max_pts_semana = valor_sesion * 2

    semanas_pts = [sum(valores[idx: idx + 2]) for idx in range(0, len(valores), 2)]

    pct_semanas: list[float] = []
    acumulado = 0.0
    max_acumulado = 0.0
    for pts in semanas_pts[:total_semanas_modelo]:
        acumulado += pts
        max_acumulado += max_pts_semana
        pct_semanas.append(round((acumulado / max_acumulado) * 100, 1) if max_acumulado > 0 else 0.0)

    mid_idx = len(pct_semanas) // 2
    pct_mitad = pct_semanas[mid_idx] if pct_semanas else 0.0
    tendencia = _calcular_tendencia(pct_semanas)
    racha_max = _racha_max_faltas(valores)

    carrera = alumno.carrera or "Sin carrera"
    try:
        carrera_enc = int(_encoder.transform([carrera])[0])
    except Exception:
        carrera_enc = -1

    features: dict[str, float] = {
        "pct_mitad": pct_mitad,
        "tendencia": tendencia,
        "racha_max_faltas": racha_max,
        "carrera_enc": carrera_enc,
    }

    for idx, column in enumerate(_week_feature_cols(), start=1):
        features[column] = pct_semanas[idx - 1] if idx <= len(pct_semanas) else np.nan

    return features


def cargar_artefactos():
    recargar_modelo()


# Cargar al importar el módulo
cargar_artefactos()


def predecir_upload(db: Session, upload_id: int) -> dict[str, Any]:
    if not modelo_disponible():
        raise Exception("Modelo de predicción no disponible")

    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise FileNotFoundError("Upload no encontrado")

    if upload.semestre_id and upload.horario_id:
        grupos_ids = [
            grupo_id
            for (grupo_id,) in db.query(GrupoSemestre.id).filter(
                GrupoSemestre.semestre_id == upload.semestre_id,
                GrupoSemestre.horario_id == upload.horario_id,
            ).all()
        ]
        alumnos_query = db.query(Alumno).filter(Alumno.grupo_semestre_id.in_(grupos_ids))
    else:
        alumnos_query = db.query(Alumno).join(Grupo, Alumno.grupo_id == Grupo.id).filter(Grupo.upload_id == upload_id)

    alumnos_list = alumnos_query.filter(Alumno.activo.is_(True)).all()

    if not alumnos_list:
        raise ValueError("El upload no tiene alumnos activos para predecir.")

    conteo = {"alto": 0, "medio": 0, "bajo": 0}
    columnas_modelo = _feature_cols()

    for alumno in alumnos_list:
        grupo_nombre = "Desconocido"
        if alumno.grupo:
            grupo_nombre = alumno.grupo.nombre
        elif alumno.grupo_semestre:
            grupo_nombre = alumno.grupo_semestre.nombre

        features = _build_features(alumno)
        row = {columna: features.get(columna, np.nan) for columna in columnas_modelo}
        df = pd.DataFrame([row], columns=columnas_modelo)

        df_imputed = _imputer.transform(df)
        prob = float(_modelo.predict_proba(df_imputed)[0][1] * 100)
        pred = int(_modelo.predict(df_imputed)[0])

        nivel = "Bajo"
        if prob >= 70:
            nivel = "Alto"
            conteo["alto"] += 1
        elif prob >= 40:
            nivel = "Medio"
            conteo["medio"] += 1
        else:
            conteo["bajo"] += 1

        pred_obj = db.query(Prediccion).filter(
            Prediccion.upload_id == upload_id,
            Prediccion.alumno_id == alumno.id,
        ).first()

        if not pred_obj:
            pred_obj = Prediccion(upload_id=upload_id, alumno_id=alumno.id)
            db.add(pred_obj)

        pred_obj.grupo_nombre = grupo_nombre
        pred_obj.prob_riesgo = prob
        pred_obj.nivel_riesgo = nivel
        pred_obj.prediccion = pred
        pred_obj.semestre_label = upload.semestre_label

    db.commit()

    return {
        "upload_id": upload_id,
        "total_alumnos": len(alumnos_list),
        "alto": conteo["alto"],
        "medio": conteo["medio"],
        "bajo": conteo["bajo"],
        "created_at": datetime.now().isoformat(),
    }
