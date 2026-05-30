from datetime import date, datetime
from enum import Enum

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


class ModoResumenMarn(str, Enum):
    portal = "portal"
    snet = "snet"
    no_disponible = "no_disponible"
    off = "off"


class ItemMarnExtraccion(BaseModel):
    tipo: str
    titulo: str
    detalle: str | None = None
    url: str | None = None


class EstacionSrtDiaria(BaseModel):
    indice: str
    nombre: str
    fecha_reporte: str | None = None
    lluvia_mm: float | None = None
    temp_max_dia_anterior_c: float | None = None
    temp_min_dia_actual_c: float | None = None
    humedad_relativa_pct: float | None = None
    distancia_km: float | None = None
    latitud_estacion: float | None = None
    longitud_estacion: float | None = None


class ResumenMarnApiV1(BaseModel):
    schema_version: str = "1.0"
    generado_en: datetime
    consulta: dict
    modo: ModoResumenMarn
    fuente_oficial: str | None = None
    url_portal_consultado: str | None = None
    items: list[ItemMarnExtraccion]
    nota_metodologica: str | None = None
    estacion_srt_cercana: EstacionSrtDiaria | None = None
    url_datos_srt: str | None = None


class EstadoIntegracionMarn(BaseModel):
    marn_complemento_configurado: bool


class UbicacionDisponible(BaseModel):
    nombre: str
    latitud: float
    longitud: float
    altitud: float
    region: str


class DatoPronosticoSiembra(BaseModel):
    fecha: date
    temp_max: float
    temp_min: float
    lluvia_mm: float
    humedad: int
    velocidad_viento: float


class RespuestaUbicaciones(BaseModel):
    total: int
    ubicaciones: list[UbicacionDisponible]


class RespuestaPronosticoApi(BaseModel):
    ubicacion: str
    latitud: float
    longitud: float
    region: str
    ultima_actualizacion: datetime | None
    fuente: str = "Open-Meteo"
    datos_reales: bool = True
    confiable: bool = Field(
        default=True,
        description="True si los datos provienen del batch reciente o consulta directa válida",
    )
    origen: str = Field(
        description="base_datos = cache del batch; open_meteo_tiempo_real = consulta directa reciente"
    )
    ubicacion_referencia: str | None = Field(
        default=None,
        description="Ciudad del batch usada como referencia para parcelas en el mapa",
    )
    advertencia: str | None = Field(
        default=None,
        description="Aviso al usuario sobre antigüedad o referencia espacial",
    )
    dias: int
    datos: list[DatoPronosticoSiembra]


class RespuestaPronosticoParcela(BaseModel):
    """Pronóstico de parcela en mapa: solo lectura SQLite (ciudad batch más cercana)."""

    latitud: float
    longitud: float
    altitud: float
    ubicacion: str
    region: str
    ubicacion_referencia: str
    region_referencia: str = Field(description="Departamento/zona de la ciudad batch usada")
    distancia_km: float
    resumen: str = Field(description="Línea corta: parcela y ciudad de referencia del pronóstico")
    advertencia: str | None = None
    ultima_actualizacion: datetime | None
    fuente: str = "Open-Meteo"
    datos_reales: bool = True
    confiable: bool = True
    origen: str = "ciudad_referencia_batch"
    dias: int
    pronostico: list[DatoPronosticoSiembra]
