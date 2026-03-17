# universidad-saludable-api

Microservicio **FastAPI + PostgreSQL** para procesar listas de asistencia del Departamento de Universidad Saludable y exponerlas vía REST para consumo desde Spring Boot.

---

## Requisitos

- Python 3.11+
- Docker (para PostgreSQL)
- pip

---

## Configuración Inicial

### 1. Clonar el repositorio y crear entorno virtual

```bash
git clone <url-del-repo>
cd universidad-saludable-api

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env si es necesario (por defecto funciona con docker-compose)
```

Contenido de `.env`:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/universidad_saludable
APP_PORT=8000
```

### 4. Levantar PostgreSQL con Docker

```bash
docker compose up -d
```

Esto levanta solo la base de datos en el puerto **5432**.

### 5. Ejecutar migraciones

```bash
alembic upgrade head
```

Esto crea las tablas: `uploads`, `grupos`, `alumnos`, `asistencias`.

### 6. Levantar el servidor

```bash
python main.py
```

La API queda disponible en **http://localhost:8000**

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## Uso Básico

### Subir un archivo Excel

```bash
curl -X POST http://localhost:8000/api/v1/uploads \
  -F "file=@lista_asistencia.xlsx" \
  -F "semestre_label=Enero-Mayo 2025"
```

**Respuesta:**
```json
{
  "id": 1,
  "filename": "lista_asistencia.xlsx",
  "uploaded_at": "2025-03-11T13:54:40Z",
  "semestre_label": "Enero-Mayo 2025",
  "grupos_found": 5,
  "total_alumnos": 87
}
```

### Lista de uploads

```bash
curl http://localhost:8000/api/v1/uploads
```

### Grupos de un upload

```bash
curl http://localhost:8000/api/v1/uploads/1/grupos
```

### Alumnos de un grupo (con filtro opcional)

```bash
curl http://localhost:8000/api/v1/grupos/1/alumnos
curl "http://localhost:8000/api/v1/grupos/1/alumnos?carrera=Informatica"
```

### Asistencias de un alumno

```bash
curl http://localhost:8000/api/v1/alumnos/1/asistencias
```

### Análisis comparativo de talleres

```bash
curl http://localhost:8000/api/v1/uploads/1/talleres
```

---

## Migraciones con Alembic

```bash
# Crear nueva migración automática (tras cambios en models/__init__.py)
alembic revision --autogenerate -m "descripcion"

# Aplicar migraciones
alembic upgrade head

# Ver historial
alembic history

# Revertir una migración
alembic downgrade -1
```

---

## Estructura del Proyecto

```
universidad-saludable-api/
├── app/
│   ├── api/v1/router.py       # Endpoints REST
│   ├── core/config.py         # Configuración desde .env
│   ├── db/session.py          # Sesión SQLAlchemy
│   ├── models/__init__.py     # Modelos ORM
│   ├── schemas/__init__.py    # Schemas Pydantic
│   ├── services/
│   │   ├── excel_parser.py    # Parser del Excel
│   │   └── upload_service.py  # Persistencia
│   └── main.py                # App FastAPI
├── alembic/                   # Migraciones
├── docker-compose.yml         # PostgreSQL
├── main.py                    # Entrypoint uvicorn
├── requirements.txt
├── .env.example
├── CLAUDE.md                  # Contexto técnico
└── README.md
```

---

## Formato del Excel Esperado

| Fila | Contenido |
|------|-----------|
| 0 | Header visual (horario + semana labels) — **ignorar** |
| 1 | Nombres reales de columnas |
| 2+ | Un alumno por fila |

**Columnas conservadas:** Folio, Nombre, Matricula, Semestre, Carrera + 23 fechas de sesión + ASISTENCIA, NUTRICIÓN, FISIO, LIMPIEZA, COAE, TALLER, TOTAL

**Columnas descartadas:** vacías, Telefono, Cuestionario, Album Entregado, e42, y días de asueto.

Si una hoja no tiene el formato esperado, **se omite con un log** en lugar de fallar el upload completo.

---

## Integración con Spring Boot

Los responses son JSON estándar. Las fechas se devuelven en ISO 8601:
- `date` → `"2025-03-03"`
- `datetime` → `"2025-03-11T13:54:40Z"`

Los valores numéricos (`Decimal`) se serializan como números JSON estándar.
