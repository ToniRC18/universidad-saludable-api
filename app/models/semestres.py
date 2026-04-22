from sqlalchemy import Column, Integer, String, Boolean, Date, Numeric, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from decimal import Decimal

from app.db.session import Base

class Carrera(Base):
    __tablename__ = "carreras"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), unique=True, nullable=False)
    facultad = Column(String(255), nullable=False)
    activa = Column(Boolean, default=True, nullable=False)


class Semestre(Base):
    __tablename__ = "semestres"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), nullable=False)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)
    total_semanas = Column(Integer, nullable=False)
    puntaje_maximo_asistencia = Column(Numeric(6, 2), default=60.0, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    tiene_talleres = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    horarios = relationship("Horario", back_populates="semestre", cascade="all, delete-orphan")
    grupos = relationship("GrupoSemestre", back_populates="semestre", cascade="all, delete-orphan")

    @hybrid_property
    def total_sesiones(self):
        if self.total_semanas is None:
            return 0
        return self.total_semanas * 2

    @hybrid_property
    def valor_por_sesion(self):
        if not self.puntaje_maximo_asistencia or not self.total_sesiones:
            return Decimal("0.00")
        valor = Decimal(self.puntaje_maximo_asistencia) / Decimal(self.total_sesiones)
        return round(valor, 2)


class Horario(Base):
    __tablename__ = "horarios"

    id = Column(Integer, primary_key=True, index=True)
    semestre_id = Column(Integer, ForeignKey("semestres.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(255), nullable=False)
    # Días — dia_1 es el único obligatorio, el resto opcionales para soportar 1 hasta 4 días
    dia_1 = Column(String(50), nullable=False)
    dia_2 = Column(String(50), nullable=True)
    dia_3 = Column(String(50), nullable=True)
    dia_4 = Column(String(50), nullable=True)

    semestre = relationship("Semestre", back_populates="horarios")
    grupos = relationship("GrupoSemestre", back_populates="horario", cascade="all, delete-orphan")


class GrupoSemestre(Base):
    __tablename__ = "grupos_semestre"

    id = Column(Integer, primary_key=True, index=True)
    semestre_id = Column(Integer, ForeignKey("semestres.id", ondelete="CASCADE"), nullable=False)
    horario_id = Column(Integer, ForeignKey("horarios.id", ondelete="CASCADE"), nullable=True)
    nombre = Column(String(255), nullable=False)
    tipo = Column(String(100), nullable=False)
    sub_bloque = Column(Integer, nullable=True) # 1 o 2

    semestre = relationship("Semestre", back_populates="grupos")
    horario = relationship("Horario", back_populates="grupos")


class UploadsHorario(Base):
    __tablename__ = "uploads_horario"

    id = Column(Integer, primary_key=True, index=True)
    semestre_id = Column(Integer, ForeignKey("semestres.id", ondelete="CASCADE"), nullable=False)
    horario_id = Column(Integer, ForeignKey("horarios.id", ondelete="CASCADE"), nullable=False)
    ultima_fecha_subida = Column(Date, nullable=True)
    ultimo_upload_at = Column(DateTime(timezone=True), nullable=True)
    total_alumnos = Column(Integer, nullable=True)

