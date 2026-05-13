from datetime import date, datetime
from enum import Enum
from typing import Any

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


class RespuestaMarnComplemento(BaseModel):
    """Respuesta adicional; no forma parte de /forecast ni de los demás endpoints existentes."""

    ubicacion: dict
    fuente: str = "MARN (red nacional)"
    disponible: bool
    mensaje: str | None = None
    datos: dict[str, Any] | None = None


class EstadoIntegracionMarn(BaseModel):
    marn_complemento_configurado: bool
    api_intermedio_publica: str = "/api/v1/nacional/marn/resumen"
    nota: str = (
        "Opcional: defina MARN_COMPLEMENTO_URL con la URL absoluta de api_intermedio_publica "
        "(mismo host) para que POST /marn/complemento reenvíe este JSON sin duplicar lógica."
    )


class ModoResumenMarn(str, Enum):
    """Origen del resumen entregado por la API pública intermedia."""

    portal = "portal"
    demo = "demo"
    no_disponible = "no_disponible"
    off = "off"


class ItemMarnExtraccion(BaseModel):
    """Elemento informativo extraído del portal o generado en modo demo."""

    tipo: str = Field(..., description="enlace | texto | aviso")
    titulo: str
    detalle: str | None = None
    url: str | None = None


class ResumenMarnApiV1(BaseModel):
    """
    Contrato estable v1 para el backend intermedio nacional (referencia MARN vía portal público).
    No sustituye pronósticos numéricos de Open-Meteo.
    """

    schema_version: str = Field("1.0", description="Versión del esquema de esta respuesta.")
    generado_en: datetime
    consulta: dict[str, float]
    fuente_oficial: str = Field(
        default=(
            "Ministerio de Medio Ambiente y Recursos Naturales (MARN), El Salvador — "
            "lectura derivada del portal público"
        ),
        description="Institución de referencia; el contenido puede ser resumen no oficial.",
    )
    modo: ModoResumenMarn
    url_portal_consultado: str | None = None
    items: list[ItemMarnExtraccion] = Field(default_factory=list)
    nota_metodologica: str = Field(
        ...,
        description="Cómo se obtuvo la información y limitaciones.",
    )
