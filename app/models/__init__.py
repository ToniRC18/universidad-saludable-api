from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Column,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    semestre_label = Column(String(100), nullable=True)
    semestre_id = Column(Integer, ForeignKey("semestres.id", ondelete="SET NULL"), nullable=True)
    horario_id = Column(Integer, ForeignKey("horarios.id", ondelete="SET NULL"), nullable=True)

    grupos = relationship("Grupo", back_populates="upload", cascade="all, delete-orphan")
    semestre = relationship("Semestre")
    horario = relationship("Horario")


class Grupo(Base):
    __tablename__ = "grupos"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(255), nullable=False)
    horario = Column(Text, nullable=True)
    max_asistencia = Column(Numeric(6, 2), nullable=True)  # sesiones_reales * 2.5

    upload = relationship("Upload", back_populates="grupos")
    alumnos = relationship("Alumno", back_populates="grupo", cascade="all, delete-orphan")


class Alumno(Base):
    __tablename__ = "alumnos"

    id = Column(Integer, primary_key=True, index=True)
    grupo_id = Column(Integer, ForeignKey("grupos.id", ondelete="CASCADE"), nullable=True)
    grupo_semestre_id = Column(Integer, ForeignKey("grupos_semestre.id", ondelete="CASCADE"), nullable=True)
    folio = Column(String(50), nullable=True)
    nombre = Column(String(255), nullable=True)
    matricula = Column(String(50), nullable=True)
    semestre = Column(String(50), nullable=True)
    carrera = Column(String(255), nullable=True)
    total_asistencia = Column(Numeric(6, 2), nullable=True)
    nutricion = Column(Numeric(6, 2), nullable=True)
    fisio = Column(Numeric(6, 2), nullable=True)
    limpieza = Column(Numeric(6, 2), nullable=True)
    coae = Column(Numeric(6, 2), nullable=True)
    taller = Column(Numeric(6, 2), nullable=True)
    total = Column(Numeric(6, 2), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)

    grupo = relationship("Grupo", back_populates="alumnos")
    grupo_semestre = relationship("GrupoSemestre")
    asistencias = relationship("Asistencia", back_populates="alumno", cascade="all, delete-orphan")


class Asistencia(Base):
    __tablename__ = "asistencias"

    id = Column(Integer, primary_key=True, index=True)
    alumno_id = Column(Integer, ForeignKey("alumnos.id", ondelete="CASCADE"), nullable=False)
    fecha = Column(Date, nullable=False)
    valor = Column(Numeric(4, 2), nullable=False, default=0)

    alumno = relationship("Alumno", back_populates="asistencias")


# Módulo de pruebas físicas
from app.models.pruebas import (  # noqa: E402,F401
    Seguimiento,
    SeguimientoGrupo,
    PruebaFisica,
    PeriodoSeguimiento,
    ResultadoPrueba,
)

# Módulo de semestres y catálogos
from app.models.semestres import (  # noqa: E402,F401
    Carrera,
    Semestre,
    Horario,
    GrupoSemestre,
    UploadsHorario,
)


class Prediccion(Base):
    __tablename__ = "predicciones"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    alumno_id = Column(Integer, ForeignKey("alumnos.id", ondelete="CASCADE"), nullable=False)
    grupo_nombre = Column(String(255), nullable=True)
    prob_riesgo = Column(Numeric(6, 2), nullable=True)
    nivel_riesgo = Column(String(50), nullable=True)
    prediccion = Column(Integer, nullable=True)
    semestre_label = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    upload = relationship("Upload")
    alumno = relationship("Alumno")

    __table_args__ = (
        UniqueConstraint("upload_id", "alumno_id", name="ix_predicciones_upload_alumno"),
    )
