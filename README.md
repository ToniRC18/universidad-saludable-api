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
│   │   ├── __init__.py             # ORM: Upload, Grupo, Alumno, Asistencia
│   │   └── pruebas.py              # ORM: Seguimiento, SeguimientoGrupo, PruebaFisica, PeriodoSeguimiento, ResultadoPrueba
│   ├── schemas/
│   │   ├── __init__.py             # Pydantic response models (asistencia)
│   │   └── pruebas.py              # Pydantic schemas del módulo de pruebas físicas
│   └── services/
│       ├── excel_parser.py         # Parseo tolerante del Excel por hojas
│       ├── upload_service.py       # Persistencia del Excel parseado en BD
│       ├── stats_service.py        # Consultas de análisis estadístico
│       ├── pruebas_service.py      # Lógica de negocio del módulo de pruebas físicas
│       └── plantilla_service.py    # Generación y parseo del Excel plantilla
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 57c94bd6b379_initial_schema.py
│       └── b4f9c2d8e1a3_pruebas_fisicas.py
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

Esto crea las 9 tablas: `uploads`, `grupos`, `alumnos`, `asistencias`, `seguimientos`, `seguimiento_grupos`, `pruebas_fisicas`, `periodos_seguimiento`, `resultados_prueba`.

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
| total | NUMERIC | Suma de talleres (NUTRICIÓN+FISIO+LIMPIEZA+COAE+TALLER). Máx. 40 pts. Independiente de asistencia. Expuesto en la API como `total_talleres` |

### `asistencias`
Una fila por alumno por fecha de sesión.

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| alumno_id | INTEGER FK | Referencia a `alumnos` |
| fecha | DATE | Fecha de la sesión (formato YYYY-MM-DD) |
| valor | NUMERIC | 2.5 = asistió, 0 = falta |

---

## Módulo de pruebas físicas — Modelo de base de datos

### `seguimientos`
Configuración de un seguimiento de pruebas físicas (ej. "Pruebas físicas Enero-Mayo 2025").

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| nombre | VARCHAR | Nombre descriptivo del seguimiento |
| descripcion | TEXT | Descripción opcional |
| aplica_a_todos | BOOLEAN | Si aplica a todos los grupos del departamento |
| activo | BOOLEAN | Estado activo/inactivo |
| created_at | TIMESTAMP | Fecha de creación |

### `seguimiento_grupos`
Grupos de alumnos que participan en un seguimiento.

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| seguimiento_id | INTEGER FK | Referencia a `seguimientos` |
| nombre_grupo | VARCHAR | Nombre del grupo (ej. "ATLETISMO 1") |
| descripcion | TEXT | Descripción opcional del grupo |

### `pruebas_fisicas`
Pruebas configuradas para un seguimiento (ej. "Flexiones", "Resistencia 1km").

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| seguimiento_id | INTEGER FK | Referencia a `seguimientos` |
| nombre | VARCHAR | Nombre de la prueba |
| unidad | VARCHAR | Unidad de medida (ej. "reps/min", "segundos", "metros") |
| mayor_es_mejor | BOOLEAN | Indica si un valor más alto significa mejor resultado |

### `periodos_seguimiento`
Momentos de medición dentro de un semestre (Inicial, Medio, Final).

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| seguimiento_id | INTEGER FK | Referencia a `seguimientos` |
| semestre_label | VARCHAR | Etiqueta del semestre (ej. "Enero-Mayo 2025") |
| nombre_periodo | VARCHAR | Nombre del momento (ej. "Inicial", "Medio", "Final") |
| fecha | DATE | Fecha de aplicación de las pruebas |

### `resultados_prueba`
Resultado individual de un alumno en una prueba para un periodo dado.

| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| periodo_id | INTEGER FK | Referencia a `periodos_seguimiento` |
| prueba_id | INTEGER FK | Referencia a `pruebas_fisicas` |
| grupo_id | INTEGER FK nullable | Referencia a `seguimiento_grupos` — FK nullable necesaria para poder filtrar y agrupar en los endpoints de análisis (`/progreso`, `/ranking-mejora`) |
| matricula | VARCHAR | Matrícula del alumno |
| nombre_alumno | VARCHAR | Nombre del alumno |
| genero | VARCHAR | Género (opcional) |
| edad | INTEGER | Edad (opcional) |
| valor | NUMERIC | Resultado obtenido (NULL si la celda no era numérica) |

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

### Pruebas físicas (`/api/v1/pruebas`)

#### Gestión de seguimientos

#### `POST /pruebas/seguimientos`
Crea un nuevo seguimiento de pruebas físicas.
- **Body JSON:** `nombre`, `descripcion` (opcional), `aplica_a_todos` (bool)
- **Response:** Detalle completo del seguimiento creado

#### `GET /pruebas/seguimientos`
Lista todos los seguimientos con conteo de grupos y pruebas configuradas.

#### `GET /pruebas/seguimientos/{seguimiento_id}`
Detalle de un seguimiento: sus grupos y pruebas físicas configuradas.
- **Errores:** 404 si no existe

#### `PATCH /pruebas/seguimientos/{seguimiento_id}`
Actualiza nombre, descripción o estado activo/inactivo. Solo los campos enviados se modifican.
- **Body JSON:** `nombre`, `descripcion`, `activo` (todos opcionales)
- **Errores:** 404 si no existe

#### Grupos del seguimiento

#### `POST /pruebas/seguimientos/{seguimiento_id}/grupos`
Agrega un grupo al seguimiento.
- **Body JSON:** `nombre_grupo`, `descripcion` (opcional)
- **Errores:** 404 si no existe el seguimiento

#### `DELETE /pruebas/seguimientos/{seguimiento_id}/grupos/{grupo_id}`
Elimina un grupo del seguimiento y sus resultados asociados (cascade).
- **Errores:** 404 si no existe el seguimiento o el grupo

#### Pruebas del seguimiento

#### `POST /pruebas/seguimientos/{seguimiento_id}/pruebas`
Agrega una prueba física al seguimiento.
- **Body JSON:** `nombre`, `unidad` (opcional), `mayor_es_mejor` (bool)
- **Errores:** 404 si no existe el seguimiento

#### `DELETE /pruebas/seguimientos/{seguimiento_id}/pruebas/{prueba_id}`
Elimina una prueba del seguimiento y sus resultados asociados (cascade).
- **Errores:** 404 si no existe el seguimiento o la prueba

#### Periodos

#### `POST /pruebas/seguimientos/{seguimiento_id}/periodos`
Crea un periodo de medición (ej. Inicial, Medio, Final).
- **Body JSON:** `semestre_label`, `nombre_periodo`, `fecha` (YYYY-MM-DD)
- **Errores:** 404 si no existe el seguimiento

#### `GET /pruebas/seguimientos/{seguimiento_id}/periodos`
Lista todos los periodos del seguimiento agrupados por `semestre_label`.
- **Errores:** 404 si no existe el seguimiento

#### Plantilla Excel

#### `GET /pruebas/periodos/{periodo_id}/plantilla`
Genera y descarga un archivo Excel (.xlsx) con una hoja por grupo, columnas fijas (Matricula, Nombre, Genero, Edad) más una columna por prueba física, y metadatos en la fila 0.
- **Response:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- **Errores:** 404 si no existe el periodo; 400 si el seguimiento no tiene grupos configurados

#### `POST /pruebas/periodos/{periodo_id}/resultados`
Recibe el Excel llenado (mismo formato que la plantilla), lo parsea y guarda los resultados.
- **Body:** `multipart/form-data` con campo `file` (.xlsx)
- **Response:** `{ total_procesadas, total_guardadas, total_saltadas }`
- **Tolerancia:** filas con matrícula vacía se saltan y loguean; celdas no numéricas se guardan como NULL; nunca falla por una fila mala
- **Errores:** 404 si no existe el periodo; 400 si el archivo no es Excel o está vacío

#### Análisis

#### `GET /pruebas/seguimientos/{seguimiento_id}/progreso`
Progreso por alumno entre los periodos de un semestre. Devuelve por alumno, por prueba: el valor en cada periodo y la diferencia entre el primero y el último con dato.
- **Query params:** `semestre_label` (requerido), `grupo_id` (int, opcional)
- **Errores:** 404 si no existe el seguimiento

#### `GET /pruebas/seguimientos/{seguimiento_id}/ranking-mejora`
Ranking de grupos por mejora promedio entre el primer y último periodo de un semestre. Ordenado de mayor a menor diferencia.
- **Query params:** `semestre_label` (requerido)
- **Response:** por grupo y prueba: promedio inicial, promedio final, diferencia y porcentaje de mejora
- **Errores:** 404 si no existe el seguimiento; devuelve lista vacía si hay menos de 2 periodos

#### `GET /pruebas/seguimientos/{seguimiento_id}/historico`
Comparativo del promedio por prueba entre semestres distintos. Usa el periodo final (mayor fecha) de cada semestre. Útil para ver la evolución a lo largo de varios semestres.
- **Errores:** 404 si no existe el seguimiento

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
- Los promedios en todos los endpoints de stats se redondean a 1 decimal.
- Todos los endpoints de stats devuelven 404 si el `upload_id` no existe.
- Para agregar nuevos endpoints de estadísticas: la lógica va en `stats_service.py` y el registro de rutas en `router.py`. No tocar modelos ni schemas existentes salvo que sea necesario.
- El archivo `CLAUDE.md` en la raíz tiene el contexto técnico del proyecto para usarlo con Claude Code en futuras sesiones.

### Interpretación correcta de ASISTENCIA vs TOTAL (talleres)

Estas son **dos métricas completamente independientes** que nunca se suman:

- **`total_asistencia`** — Suma de puntos de asistencia a las sesiones. Máximo **60 pts** (24 sesiones × 2.5 pts, incluyendo el día de asueto que el Excel contabiliza). El porcentaje se calcula siempre como `(total_asistencia / 60) * 100`.
- **`total` en BD / `total_talleres` en la API** — Suma de los 5 talleres complementarios: NUTRICIÓN + FISIO + LIMPIEZA + COAE + TALLER. Máximo **40 pts**. El porcentaje se calcula como `(total_talleres / 40) * 100`. **No es una calificación global ni incluye asistencia.**
- La columna del Excel llamada `TOTAL` corresponde exclusivamente a la suma de talleres. No es `asistencia + talleres`.
- En `AlumnoOut` el campo se expone como `total_talleres` (renombrado respecto a la columna de BD `total`) para que la semántica sea explícita. Los campos `porcentaje_asistencia` y `porcentaje_talleres` se calculan automáticamente en el schema.