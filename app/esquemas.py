from datetime import date

from pydantic import BaseModel, Field


class SolicitudClima(BaseModel):
    latitud: float = Field(..., ge=13.0, le=14.5)
    longitud: float = Field(..., ge=-90.3, le=-87.5)
    altitud: float = Field(..., ge=0, le=3500)
    dias: int = Field(7, ge=1, le=31)


class DiaPronostico(BaseModel):
    fecha: date
    temperatura_max: float
    temperatura_min: float
    lluvia_mm: float
    humedad_relativa: float


class RespuestaPronostico(BaseModel):
    ubicacion: dict
    fuente: str = "Open-Meteo"
    dias: list[DiaPronostico]


class DiaAjustado(BaseModel):
    fecha: date
    temperatura_pronosticada: float
    temperatura_ajustada: float
    lluvia_pronosticada_mm: float
    probabilidad_lluvia_ajustada: float
    humedad_relativa: float


class RespuestaAjustada(BaseModel):
    ubicacion: dict
    modelo: str
    dias: list[DiaAjustado]


class RecomendacionDia(BaseModel):
    fecha: date
    apto_siembra: bool
    puntaje: float
    razon: str


class RespuestaSiembra(BaseModel):
    ubicacion: dict
    recomendaciones: list[RecomendacionDia]


class RiesgoClimatico(BaseModel):
    nivel: str
    puntaje: float
    descripcion: str


class PuntoTemperatura(BaseModel):
    fecha: date
    temperatura_c: float


class LluviaMensual(BaseModel):
    mes: str
    lluvia_mm: float


class ComparacionAnual(BaseModel):
    total_actual_mm: float
    total_anterior_mm: float
    diferencia_mm: float
    variacion_porcentual: float


class RespuestaInsights(BaseModel):
    ubicacion: dict
    region_microclima: str
    riesgo_sequia: RiesgoClimatico
    riesgo_exceso_lluvia: RiesgoClimatico
    temperatura_proximos_dias: list[PuntoTemperatura]
    lluvia_mensual_actual: list[LluviaMensual]
    lluvia_mensual_anterior: list[LluviaMensual]
    comparacion_anual: ComparacionAnual
    notificaciones: list[str]
