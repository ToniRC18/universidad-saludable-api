"""
Excel parser for Universidad Saludable attendance sheets.

Expected structure per sheet:
  Row 0  → visual header (schedule + "Semana 1"..."Semana 12") — IGNORED
  Row 1  → real column names
  Rows 2+→ one student per row
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Columns to DISCARD (case-insensitive substring match on header name)
# Album Entregado y Cuestionario se descartan si existen; si no están presentes, no ocurre nada.
DISCARD_PATTERNS = [
    r"^$",                          # blank / empty header
    r"telefono",
    r"cuestionario",                # optional column — descartada si existe
    r"album\s*entregado",           # optional column — descartada si existe
    r"e42",
    r"inhabil|inh[aá]bil|asueto",   # días inhábiles (cualquier variante con/sin tilde)
]

# Columns we ALWAYS want to keep (exact names used in the Excel)
SUMMARY_COLS = {
    "ASISTENCIA",
    "NUTRICIÓN",
    "FISIO",
    "LIMPIEZA",
    "COAE",
    "TALLER",
    "TOTAL",
}

# Metadata columns (exact names)
META_COLS = {"Folio", "Nombre", "Matricula", "Semestre", "Carrera"}

# Month name → month number  (Spanish abbreviations used in the Excel)
MONTH_MAP = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
    # Common abbreviations that appear in the Excel
    "marz": 3, "abrl": 4, "agos": 8,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ascii_key(text: str) -> str:
    """Return accent-stripped, uppercased key for alias lookups."""
    nfkc = unicodedata.normalize("NFKC", text.strip())
    nfd = unicodedata.normalize("NFD", nfkc)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").upper()


# Maps accent-stripped uppercase variants → canonical short name (uppercase, with accents).
_CARRERA_ALIAS: dict[str, str] = {
    # Enfermería
    "ENFERMERIA": "ENFERMERÍA",
    "LICENCIATURA EN ENFERMERIA": "ENFERMERÍA",
    # Médico Cirujano (absorbe "Medicina")
    "MEDICINA": "MÉDICO CIRUJANO",
    "MEDICO CIRUJANO": "MÉDICO CIRUJANO",
    # Teología
    "TEOLOGIA": "TEOLOGÍA",
    "LICENCIATURA EN TEOLOGIA": "TEOLOGÍA",
    # Psicología Clínica
    "PSICOLOGIA CLINICA": "PSICOLOGÍA CLÍNICA",
    "LICENCIATURA EN PSICOLOGIA CLINICA": "PSICOLOGÍA CLÍNICA",
    # Psicología Educativa
    "PSICOLOGIA EDUCATIVA": "PSICOLOGÍA EDUCATIVA",
    "LICENCIATURA EN PSICOLOGIA EDUCATIVA": "PSICOLOGÍA EDUCATIVA",
    # Químico Clínico Biólogo
    "QCB": "QUÍMICO CLÍNICO BIÓLOGO",
    "QUIMICO CLINICO BIOLOGO": "QUÍMICO CLÍNICO BIÓLOGO",
    "LICENCIATURA EN QUIMICO CLINICO BIOLOGO": "QUÍMICO CLÍNICO BIÓLOGO",
    # Negocios Internacionales (incluye typo "Negiocios")
    "NEGIOCIOS": "NEGOCIOS INTERNACIONALES",
    "NEGOCIOS": "NEGOCIOS INTERNACIONALES",
    "LICENCIATURA EN NEGOCIOS INTERNACIONALES": "NEGOCIOS INTERNACIONALES",
    # Terapia Física
    "TERAPIA FISICA": "TERAPIA FÍSICA",
    "LICENCIATURA EN TERAPIA FISICA Y REHABILITACION": "TERAPIA FÍSICA",
    # Artes Visuales
    "LIC EN ARTES VISUALES": "ARTES VISUALES",
    "LICENCIATURA EN ARTES VISUALES": "ARTES VISUALES",
    # Música
    "MUSICA": "MÚSICA",
    # Comunicación y Medios
    "COMUNICACION Y MEDIOS": "COMUNICACIÓN Y MEDIOS",
    "LICENCIATURA EN COMUNICACION Y MEDIOS": "COMUNICACIÓN Y MEDIOS",
    # Contaduría Pública
    "CONTADURIA PUBLICA": "CONTADURÍA PÚBLICA",
    "LICENCIATURA EN CONTADURIA PUBLICA": "CONTADURÍA PÚBLICA",
    # Derecho
    "LICENCIATURA EN DERECHO": "DERECHO",
    # Arquitectura
    "LICENCIATURA EN ARQUITECTURA": "ARQUITECTURA",
    # Diseño de Comunicación Visual
    "DISENO DE COMUNICACION VISUAL": "DISEÑO DE COMUNICACIÓN VISUAL",
    "LICENCIATURA EN DISENO DE COMUNICACION VISUAL": "DISEÑO DE COMUNICACIÓN VISUAL",
    # Nutrición
    "NUTRICION Y ESTILO DE VIDA": "NUTRICIÓN Y ESTILO DE VIDA",
    "LICENCIATURA EN NUTRICION Y ESTILO DE VIDA": "NUTRICIÓN Y ESTILO DE VIDA",
    # Educación Preescolar / Primaria
    "LICENCIATURA EN EDUCACION PREESCOLAR": "EDUCACIÓN PREESCOLAR",
    "LICENCIATURA EN EDUCACION PRIMARIA": "EDUCACIÓN PRIMARIA",
    # Enseñanza (Ciencias Naturales, Sociales, Matemáticas, Inglés)
    "LICENCIATURA EN ENSENANZA DE LAS CIENCIAS NATURALES": "ENSEÑANZA DE LAS CIENCIAS NATURALES",
    "LICENCIATURA EN ENSENANZA DE LAS CIENCIAS SOCIALES": "ENSEÑANZA DE LAS CIENCIAS SOCIALES",
    "EDUCACION SOCIALES": "ENSEÑANZA DE LAS CIENCIAS SOCIALES",
    "LICENCIATURA EN ENSENANZA DE LAS MATEMATICAS": "ENSEÑANZA DE LAS MATEMÁTICAS",
    "LICENCIATURA EN ENSENANZA DEL INGLES": "ENSEÑANZA DEL INGLÉS",
    # Tecnologías de la Información
    "TECNOLOGIAS DE LA INFORMACION": "TECNOLOGÍAS DE LA INFORMACIÓN",
    # Ingenierías
    "INGENIERIA EN SISTEMAS COMPUTACIONALES": "INGENIERÍA EN SISTEMAS COMPUTACIONALES",
    "INGENIERIA EN SISTEMAS": "INGENIERÍA EN SISTEMAS",
    "INGENIERIA INDUSTRIAL Y DE SISTEMAS": "INGENIERÍA INDUSTRIAL Y DE SISTEMAS",
    "INGENIERIA EN ELECTRONICA Y TELECOMUNICACIONES": "INGENIERÍA EN ELECTRÓNICA Y TELECOMUNICACIONES",
    "INGENIERIA EN GESTION DE TECNOLOGIAS DE LA INFORMACION": "INGENIERÍA EN GESTIÓN DE TECNOLOGÍAS DE LA INFORMACIÓN",
}

_SEMESTRE_ORDINAL: dict[str, str] = {
    "1": "1ER", "2": "2DO", "3": "3ER", "4": "4TO",
    "5": "5TO", "6": "6TO", "7": "7MO", "8": "8VO",
    "9": "9NO", "10": "10MO",
}


def _normalize_carrera(value: Any) -> str | None:
    """Normalize career name using alias map, then uppercase fallback."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value).strip())
    if not text or text.lower() == "none":
        return None
    canonical = _CARRERA_ALIAS.get(_ascii_key(text))
    return canonical if canonical else text.upper()


def _normalize_semestre(value: Any) -> str | None:
    """Normalize semester to '4TO SEMESTRE' format."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    m = re.match(r"^(\d+)", text)
    if m:
        num = m.group(1)
        ordinal = _SEMESTRE_ORDINAL.get(num, f"{num}TO")
        return f"{ordinal} SEMESTRE"
    return text.upper()


def _should_discard(header: str) -> bool:
    """Return True if this column header should be discarded."""
    h = str(header).strip()
    for pattern in DISCARD_PATTERNS:
        if re.search(pattern, h, re.IGNORECASE):
            return True
    return False


def _normalize_date(value: Any, year_hint: int = datetime.now().year) -> date | None:
    """
    Try to convert *value* to a Python date.

    Handles:
    - datetime objects (from openpyxl)
    - date objects
    - Strings like "3 Marz", "17 Febrero", "3/3", "2025-03-03"
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", ""):
        return None

    # ISO format
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

    # "DD/MM" or "DD/MM/YYYY"
    slash_match = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", text)
    if slash_match:
        d, m, y = slash_match.groups()
        y = int(y) if y else year_hint
        if y < 100:
            y += 2000
        try:
            return date(y, int(m), int(d))
        except ValueError:
            pass

    # "DD MonthName" or "DD MonthAbbrev" — e.g. "3 Marz", "17 Febrero"
    text_match = re.match(r"^(\d{1,2})\s+([A-Za-záéíóúñÁÉÍÓÚÑ]+)", text)
    if text_match:
        day_str, month_str = text_match.groups()
        month_num = MONTH_MAP.get(month_str.lower().rstrip("."))
        if month_num:
            try:
                return date(year_hint, month_num, int(day_str))
            except ValueError:
                pass

    logger.warning("Could not parse date value: %r", value)
    return None


def _is_date_column(header: str) -> bool:
    """
    Heuristic: a column is a 'date column' if its header can be parsed as a date
    OR looks like a date-ish string ("3 Marz", "17 Febrero", datetime repr, etc.).
    """
    if isinstance(header, (datetime, date)):
        return True
    text = str(header).strip()
    # Already parseable as date?
    if _normalize_date(text) is not None:
        return True
    return False


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

class ParsedGrupo:
    def __init__(self, nombre: str, horario: str):
        self.nombre = nombre
        self.horario = horario
        self.max_asistencia: float = 0.0   # sesiones_reales * 2.5, calculado al parsear
        self.alumnos: list[dict] = []      # list of {meta: ..., dates: ..., summary: ...}


def parse_excel(file_bytes: bytes, semestre_label: str = "") -> list[ParsedGrupo]:
    """
    Parse an Excel workbook and return a list of ParsedGrupo objects.
    Sheets with unexpected structure are skipped (logged as warnings).
    """
    import io
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    grupos: list[ParsedGrupo] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 2:
            logger.warning("Sheet '%s' has fewer than 2 rows — skipping.", sheet_name)
            continue

        horario_row = rows[0]   # Row 0: visual header
        header_row = rows[1]    # Row 1: real column names
        data_rows = rows[2:]    # Rows 2+: students

        if not any(header_row):
            logger.warning("Sheet '%s' has empty header row — skipping.", sheet_name)
            continue

        # Extract horario text (first non-None cell in row 0)
        horario = next((str(c) for c in horario_row if c is not None), "")

        # Build column index map
        col_map: dict[int, str] = {}      # col_index → role ("meta:<name>", "date:<isodate>", "summary:<name>", "skip")
        date_year = _infer_year(horario, semestre_label)

        for idx, header in enumerate(header_row):
            if header is None:
                col_map[idx] = "skip"
                continue

            # Cambio 3: normalizar header con .strip().upper() antes de cualquier comparación
            h_str = str(header).strip()
            h_upper = h_str.upper()

            if _should_discard(h_str):
                col_map[idx] = "skip"
                continue

            # Summary columns — comparar en uppercase normalizando tildes
            h_norm = h_upper.replace("Ó", "O").replace("É", "E").replace("Á", "A").replace("Í", "I").replace("Ú", "U")
            matched_summary = None
            for sc in SUMMARY_COLS:
                if sc.upper().replace("Ó", "O").replace("É", "E") == h_norm:
                    matched_summary = sc
                    break
            if matched_summary:
                col_map[idx] = f"summary:{matched_summary}"
                continue

            # Meta columns — comparar en uppercase (Folio/FOLIO/folio tratados igual)
            matched_meta = None
            for mc in META_COLS:
                if mc.upper() == h_upper:
                    matched_meta = mc
                    break
            if matched_meta:
                col_map[idx] = f"meta:{matched_meta}"
                continue

            # Date columns
            parsed_date = _normalize_date(header, year_hint=date_year)
            if parsed_date is not None:
                col_map[idx] = f"date:{parsed_date.isoformat()}"
                continue

            # Unknown column → skip
            logger.debug("Sheet '%s', col %d ('%s') not recognized — skipping.", sheet_name, idx, h_str)
            col_map[idx] = "skip"

        # Validate we have at least some useful columns
        has_meta = any(v.startswith("meta:") for v in col_map.values())
        has_dates = any(v.startswith("date:") for v in col_map.values())

        if not has_meta or not has_dates:
            logger.warning(
                "Sheet '%s' is missing meta or date columns (meta=%s, dates=%s) — skipping.",
                sheet_name, has_meta, has_dates,
            )
            continue

        # Cambio 1: max_asistencia dinámico — contar sesiones reales (date cols ya filtradas de inhábiles)
        date_col_count = sum(1 for v in col_map.values() if v.startswith("date:"))
        max_asistencia = round(date_col_count * 2.5, 2)

        grupo = ParsedGrupo(nombre=sheet_name, horario=horario)
        grupo.max_asistencia = max_asistencia

        for row in data_rows:
            # Skip completely empty rows
            if not any(c is not None for c in row):
                continue

            alumno: dict = {
                "meta": {},
                "dates": {},   # iso_date_str → numeric value
                "summary": {},
            }

            for idx, role in col_map.items():
                if idx >= len(row):
                    continue
                cell_val = row[idx]

                if role == "skip":
                    continue
                elif role.startswith("meta:"):
                    key = role[5:]
                    raw = str(cell_val).strip() if cell_val is not None else None
                    if key.lower() == "carrera":
                        alumno["meta"][key.lower()] = _normalize_carrera(raw)
                    elif key.lower() == "semestre":
                        alumno["meta"][key.lower()] = _normalize_semestre(raw)
                    else:
                        alumno["meta"][key.lower()] = raw
                elif role.startswith("date:"):
                    iso = role[5:]
                    alumno["dates"][iso] = _to_numeric(cell_val)
                elif role.startswith("summary:"):
                    key = role[8:]
                    alumno["summary"][key] = _to_numeric(cell_val)

            # Skip rows with no name and no folio (likely empty/junk rows)
            if not alumno["meta"].get("nombre") and not alumno["meta"].get("folio"):
                continue

            grupo.alumnos.append(alumno)

        if not grupo.alumnos:
            logger.warning("Sheet '%s' parsed 0 students — skipping.", sheet_name)
            continue

        grupos.append(grupo)

    return grupos


def _to_numeric(value: Any) -> float:
    """Convert a cell value to float, defaulting to 0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _infer_year(horario: str, semestre_label: str) -> int:
    """
    Try to extract the year from horario text or semestre_label.
    Defaults to current year.
    """
    for text in (horario, semestre_label):
        m = re.search(r"\b(20\d{2})\b", text)
        if m:
            return int(m.group(1))
    return datetime.now().year
