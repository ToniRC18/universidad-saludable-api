from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from app.db.session import Base


class Seguimiento(Base):
    __tablename__ = "seguimientos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), nullable=False)
    descripcion = Column(Text, nullable=True)
    aplica_a_todos = Column(Boolean, default=False, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    grupos = relationship("SeguimientoGrupo", back_populates="seguimiento", cascade="all, delete-orphan")
    pruebas = relationship("PruebaFisica", back_populates="seguimiento", cascade="all, delete-orphan")
    periodos = relationship("PeriodoSeguimiento", back_populates="seguimiento", cascade="all, delete-orphan")


class SeguimientoGrupo(Base):
    __tablename__ = "seguimiento_grupos"

    id = Column(Integer, primary_key=True, index=True)
    seguimiento_id = Column(Integer, ForeignKey("seguimientos.id", ondelete="CASCADE"), nullable=False)
    nombre_grupo = Column(String(255), nullable=False)
    descripcion = Column(Text, nullable=True)

    seguimiento = relationship("Seguimiento", back_populates="grupos")
    resultados = relationship("ResultadoPrueba", back_populates="grupo", cascade="all, delete-orphan")


class PruebaFisica(Base):
    __tablename__ = "pruebas_fisicas"

    id = Column(Integer, primary_key=True, index=True)
    seguimiento_id = Column(Integer, ForeignKey("seguimientos.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(255), nullable=False)
    unidad = Column(String(50), nullable=True)
    mayor_es_mejor = Column(Boolean, default=True, nullable=False)

    seguimiento = relationship("Seguimiento", back_populates="pruebas")
    resultados = relationship("ResultadoPrueba", back_populates="prueba", cascade="all, delete-orphan")


class PeriodoSeguimiento(Base):
    __tablename__ = "periodos_seguimiento"

    id = Column(Integer, primary_key=True, index=True)
    seguimiento_id = Column(Integer, ForeignKey("seguimientos.id", ondelete="CASCADE"), nullable=False)
    semestre_label = Column(String(100), nullable=False)
    nombre_periodo = Column(String(100), nullable=False)
    fecha = Column(Date, nullable=False)

    seguimiento = relationship("Seguimiento", back_populates="periodos")
    resultados = relationship("ResultadoPrueba", back_populates="periodo", cascade="all, delete-orphan")


class ResultadoPrueba(Base):
    __tablename__ = "resultados_prueba"

    id = Column(Integer, primary_key=True, index=True)
    periodo_id = Column(Integer, ForeignKey("periodos_seguimiento.id", ondelete="CASCADE"), nullable=False)
    prueba_id = Column(Integer, ForeignKey("pruebas_fisicas.id", ondelete="CASCADE"), nullable=False)
    # grupo_id es necesario para análisis por grupo (ranking-mejora, progreso filtrado)
    grupo_id = Column(Integer, ForeignKey("seguimiento_grupos.id", ondelete="SET NULL"), nullable=True)
    matricula = Column(String(50), nullable=False)
    nombre_alumno = Column(String(255), nullable=True)
    genero = Column(String(50), nullable=True)
    edad = Column(Integer, nullable=True)
    valor = Column(Numeric(10, 4), nullable=True)

    periodo = relationship("PeriodoSeguimiento", back_populates="resultados")
    prueba = relationship("PruebaFisica", back_populates="resultados")
    grupo = relationship("SeguimientoGrupo", back_populates="resultados")
