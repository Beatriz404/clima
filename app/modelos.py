from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.base_datos import Base


class RegistroClimatico(Base):
    __tablename__ = "registros_climaticos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[datetime] = mapped_column(Date, index=True)
    latitud: Mapped[float] = mapped_column(Float, index=True)
    longitud: Mapped[float] = mapped_column(Float, index=True)
    altitud: Mapped[float] = mapped_column(Float)
    temperatura_pronosticada: Mapped[float] = mapped_column(Float)
    lluvia_pronosticada_mm: Mapped[float] = mapped_column(Float)
    humedad_relativa: Mapped[float] = mapped_column(Float)
    temperatura_ajustada: Mapped[float] = mapped_column(Float)
    probabilidad_lluvia_ajustada: Mapped[float] = mapped_column(Float)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PronosticoSiembra(Base):
    __tablename__ = "pronosticos_siembra"
    __table_args__ = (
        UniqueConstraint("ubicacion_nombre", "fecha_pronostico", name="uq_ubicacion_fecha_pronostico"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ubicacion_nombre: Mapped[str] = mapped_column(String(80), index=True)
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    fecha_pronostico: Mapped[datetime] = mapped_column(Date, index=True)
    temp_max: Mapped[float] = mapped_column(Float)
    temp_min: Mapped[float] = mapped_column(Float)
    lluvia_mm: Mapped[float] = mapped_column(Float)
    humedad: Mapped[int] = mapped_column(Integer)
    velocidad_viento: Mapped[float] = mapped_column(Float)
    fuente_datos: Mapped[str] = mapped_column(String(50), default="Open-Meteo")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecomendacionSiembra(Base):
    __tablename__ = "recomendaciones_siembra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[datetime] = mapped_column(Date, index=True)
    latitud: Mapped[float] = mapped_column(Float, index=True)
    longitud: Mapped[float] = mapped_column(Float, index=True)
    altitud: Mapped[float] = mapped_column(Float)
    apto_siembra: Mapped[bool] = mapped_column(Boolean)
    puntaje: Mapped[float] = mapped_column(Float)
    razon: Mapped[str] = mapped_column(String(300))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
