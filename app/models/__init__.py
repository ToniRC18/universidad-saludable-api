from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
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

    grupos = relationship("Grupo", back_populates="upload", cascade="all, delete-orphan")


class Grupo(Base):
    __tablename__ = "grupos"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(255), nullable=False)
    horario = Column(Text, nullable=True)

    upload = relationship("Upload", back_populates="grupos")
    alumnos = relationship("Alumno", back_populates="grupo", cascade="all, delete-orphan")


class Alumno(Base):
    __tablename__ = "alumnos"

    id = Column(Integer, primary_key=True, index=True)
    grupo_id = Column(Integer, ForeignKey("grupos.id", ondelete="CASCADE"), nullable=False)
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

    grupo = relationship("Grupo", back_populates="alumnos")
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
