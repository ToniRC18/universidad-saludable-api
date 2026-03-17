# universidad-saludable-api

Microservicio REST construido con **FastAPI + PostgreSQL** para el **Departamento de Universidad Saludable**. Recibe archivos Excel con listas de asistencia de los grupos de actividad física, los parsea, los persiste en base de datos y expone los datos procesados para ser consumidos por un sistema externo (Spring Boot).

---

## Contexto del negocio

El Departamento de Universidad Saludable gestiona la materia obligatoria de Aptitud Física. Los alumnos son asignados a grupos de actividad (Grupos de Entrenamiento, Atletismo, Basquetbol, Voleibol, etc.). Cada semestre se registran asistencias en archivos Excel con una hoja por grupo, donde cada sesión vale 2.5 puntos. Además se registran puntos de talleres complementarios (Nutrición, Fisio, Limpieza, COAE, Taller).

Este microservicio permite cargar esos archivos y consultar los datos desde un dashboard externo.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Framework | FastAPI |
| ORM | SQLAlchemy |
| Migraciones | Alembic |
| Base de datos | PostgreSQL |
| Parseo Excel | pandas + openpyxl |
| Variables de entorno | python-dotenv |
| Servidor | Uvicorn |

---

## Estructura del proyecto

```
universidad-saludable-api/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── router.py           # Todos los endpoints REST
│   ├── core/
│   │   └── config.py               # Settings desde .env (Settings class)
│   ├── db/
│   │   └── session.py              # Engine SQLAlchemy + get_db() dependency
│   ├── models/
│   │   └── __init__.py             # ORM: Upload, Grupo, Alumno, Asistencia
│   ├── schemas/
│   │   └── __init__.py             # Pydantic response models
│   └── services/
│       ├── excel_parser.py         # Parseo tolerante del Excel por hojas
│       ├── upload_service.py       # Persistencia del Excel parseado en BD
│       └── stats_service.py        # Consultas de análisis estadístico
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 57c94bd6b379_initial_schema.py
├── main.py                         # Entrypoint uvicorn
├── requirements.txt
├── alembic.ini
├── .env                            # Variables locales (no commitear)
├── .env.example                    # Plantilla de variables
├── .gitignore
├── CLAUDE.md                       # Contexto para sesiones de Claude Code
└── README.md
```

---

## Configuración inicial

### Requisitos previos

- Python 3.10+
- PostgreSQL corriendo localmente
- La base de datos debe existir antes de correr migraciones

### 1. Clonar e instalar dependencias

```bash
git clone <repo-url>
cd universidad-saludable-api
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia `.env.example` a `.env` y llena los valores:

```bash
cp .env.example .env
```

Contenido del `.env`:

```dotenv
DATABASE_URL=postgresql://dev_pg:devpass@localhost:5432/universidad_saludable
APP_PORT=8000
```

> Ajusta usuario, contraseña y nombre de base de datos según tu entorno local.

### 3. Crear la base de datos

```sql
CREATE DATABASE universidad_saludable;
```

### 4. Correr migraciones

```bash
source .venv/bin/activate
alembic upgrade head
```

Esto crea las 4 tablas: `uploads`, `grupos`, `alumnos`, `asistencias`.

### 5. Levantar el servidor

```bash
python main.py
```

El servidor queda disponible en `http://localhost:8000`.
Documentación interactiva: `http://localhost:8000/docs`.

---

## Modelo de base de datos

### `uploads`
Registro de cada archivo Excel subido.

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| filename | VARCHAR | Nombre del archivo subido |
| uploaded_at | TIMESTAMP | Fecha y hora del upload |
| semestre_label | VARCHAR | Etiqueta manual del semestre (ej. "Enero-Mayo 2025") |

### `grupos`
Una fila por hoja del Excel (un grupo de actividad).

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| upload_id | INTEGER FK | Referencia a `uploads` |
| nombre | VARCHAR | Nombre de la hoja (ej. "G.E FEMENIL 1") |
| horario | VARCHAR | Texto del encabezado visual (ej. "LUNES Y MIERCOLES 6:00-7:00 AM") |

### `alumnos`
Un registro por alumno por grupo.

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| grupo_id | INTEGER FK | Referencia a `grupos` |
| folio | VARCHAR | Número de folio del Excel |
| nombre | VARCHAR | Nombre completo del alumno |
| matricula | VARCHAR | Matrícula universitaria |
| semestre | VARCHAR | Semestre que cursa (ej. "4TO") |
| carrera | VARCHAR | Nombre de la carrera (normalizado a mayúsculas) |
| total_asistencia | NUMERIC | Suma total de puntos de asistencia (máx. 60) |
| nutricion | NUMERIC | Puntos obtenidos en taller de Nutrición |
| fisio | NUMERIC | Puntos obtenidos en taller de Fisio |
| limpieza | NUMERIC | Puntos obtenidos en taller de Limpieza |
| coae | NUMERIC | Puntos obtenidos en taller COAE |
| taller | NUMERIC | Puntos obtenidos en Taller general |
| total | NUMERIC | Calificación final total |

### `asistencias`
Una fila por alumno por fecha de sesión.

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| alumno_id | INTEGER FK | Referencia a `alumnos` |
| fecha | DATE | Fecha de la sesión (formato YYYY-MM-DD) |
| valor | NUMERIC | 2.5 = asistió, 0 = falta |

---

## Endpoints

Todos bajo el prefijo `/api/v1`.

### Carga de datos

#### `POST /uploads`
Sube un archivo Excel y lo persiste completo en BD.

- **Body:** `multipart/form-data` con campo `file` (archivo .xlsx) y `semestre_label` (string)
- **Response:** `upload_id`, lista de grupos encontrados y total de alumnos
- **Errores:** 400 si el archivo no tiene el formato esperado

#### `GET /uploads`
Lista todos los archivos subidos.

- **Response:** Array con id, filename, uploaded_at, semestre_label

#### `GET /uploads/{upload_id}/grupos`
Lista los grupos de un archivo con conteo de alumnos.

- **Response:** Array con id, nombre, horario, total_alumnos
- **Errores:** 404 si no existe el upload

### Consulta de datos

#### `GET /grupos/{grupo_id}/alumnos`
Lista todos los alumnos de un grupo con sus totales.

- **Query params:** `?carrera=` para filtrar por carrera
- **Response:** Array con datos del alumno + totales
- **Errores:** 404 si no existe el grupo

#### `GET /alumnos/{alumno_id}/asistencias`
Devuelve todas las fechas y valores de asistencia de un alumno.

- **Response:** Array con fecha y valor por sesión
- **Errores:** 404 si no existe el alumno

#### `GET /uploads/{upload_id}/talleres`
Promedios de talleres por grupo para comparativa.

- **Response:** Por grupo: promedios de NUTRICIÓN, FISIO, LIMPIEZA, COAE, TALLER
- **Errores:** 404 si no existe el upload

### Estadísticas (`/api/v1/stats`)

#### `GET /stats/uploads/{upload_id}/asistencia-por-carrera`
Promedio de asistencia y porcentaje agrupado por carrera. El porcentaje se calcula sobre 60 pts máximo (24 sesiones × 2.5). Ordenado de mayor a menor.

#### `GET /stats/uploads/{upload_id}/tendencia-semanal`
Asistencia promedio por semana por grupo. Las semanas se reconstruyen agrupando las fechas cronológicamente en pares (2 sesiones = 1 semana). Útil para graficar líneas de tendencia.

#### `GET /stats/uploads/{upload_id}/alumnos-en-riesgo`
Alumnos con porcentaje de asistencia por debajo del umbral indicado.

- **Query params:**
  - `umbral` (float, default: 60.0) — porcentaje mínimo aceptable
  - `grupo_id` (int, opcional) — filtrar por grupo
- Ordenado de menor a mayor porcentaje.

#### `GET /stats/uploads/{upload_id}/talleres-por-carrera`
Promedio de puntos por taller (NUTRICIÓN, FISIO, LIMPIEZA, COAE, TALLER) agrupado por carrera. Los nulos se excluyen del promedio.

#### `GET /stats/uploads/{upload_id}/asistencia-por-semestre-alumno`
Promedio de asistencia agrupado por semestre que cursa el alumno. Excluye registros con semestre nulo.

#### `GET /stats/uploads/{upload_id}/ranking-grupos`
Ranking de grupos ordenados por porcentaje de asistencia promedio de sus alumnos, de mayor a menor.

---

## Formato del Excel esperado

El microservicio es tolerante: si una hoja no tiene el formato esperado la salta y la loguea, sin fallar todo el upload.

**Estructura por hoja:**
- Fila 0: encabezado visual (horario + etiquetas de semana) — se ignora
- Fila 1: nombres de columnas reales
- Filas 2+: un alumno por fila

**Columnas que se descartan en el parseo:**
- Columna 0 (vacía, artefacto del Excel)
- `Telefono` — dato personal sin valor analítico
- `Cuestionario` — casi completamente vacía
- `Album Entregado` — casi completamente vacía
- `e42` — códigos sin significado analítico claro
- `17 Marz Asueto` — día festivo, todos con valor 0

**Formato de fechas:** Las fechas vienen mixtas (algunas como datetime, otras como texto libre tipo "3 Marz"). El parser las normaliza todas a `YYYY-MM-DD`.

---

## Flujo de prueba con Swagger

1. Ir a `http://localhost:8000/docs`
2. Ejecutar `POST /api/v1/uploads` con el archivo Excel y un semestre_label
3. Copiar el `upload_id` de la respuesta
4. Ejecutar `GET /api/v1/uploads/{upload_id}/grupos` — deben aparecer 18 grupos
5. Copiar un `grupo_id` y ejecutar `GET /api/v1/grupos/{grupo_id}/alumnos`
6. Copiar un `alumno_id` y ejecutar `GET /api/v1/alumnos/{alumno_id}/asistencias`
7. Probar los endpoints de stats con el mismo `upload_id`

---

## Notas para el desarrollador

- El campo `carrera` se normaliza a mayúsculas con `str.strip().str.upper()` al parsear, para evitar duplicados por diferencias de capitalización.
- Las celdas vacías en columnas de asistencia se interpretan como `0` (falta).
- El porcentaje de asistencia siempre se calcula sobre 60 pts (máximo teórico del semestre).
- Los promedios en todos los endpoints de stats se redondean a 1 decimal.
- Todos los endpoints de stats devuelven 404 si el `upload_id` no existe.
- Para agregar nuevos endpoints de estadísticas: la lógica va en `stats_service.py` y el registro de rutas en `router.py`. No tocar modelos ni schemas existentes salvo que sea necesario.
- El archivo `CLAUDE.md` en la raíz tiene el contexto técnico del proyecto para usarlo con Claude Code en futuras sesiones.