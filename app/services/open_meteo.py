"""Capa de dominio: formatea respuestas reales de Open-Meteo vía proxy en memoria."""

from collections.abc import Callable
from datetime import datetime

from app.services.open_meteo_proxy import (
    LimiteOpenMeteoError,
    ProxyServicioNoDisponibleError,
    obtener_proxy,
)

_FORECAST_DIAS_MAX = 15

_VARIABLES_DIARIAS = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "relative_humidity_2m_mean,windspeed_10m_max"
)

__all__ = [
    "LimiteOpenMeteoError",
    "ProxyServicioNoDisponibleError",
    "obtener_pronostico",
    "obtener_pronostico_siembra",
    "obtener_historico",
    "limpiar_cache",
]


def limpiar_cache() -> None:
    try:
        obtener_proxy().limpiar_cache()
    except RuntimeError:
        pass


def _a_formato_diario(respuesta: dict, dias: int) -> list[dict]:
    diarios = respuesta["daily"]
    salida = []
    for i in range(min(dias, len(diarios["time"]))):
        salida.append(
            {
                "fecha": datetime.fromisoformat(diarios["time"][i]).date(),
                "temperatura_max": float(diarios["temperature_2m_max"][i]),
                "temperatura_min": float(diarios["temperature_2m_min"][i]),
                "lluvia_mm": float(diarios["precipitation_sum"][i] or 0),
                "humedad_relativa": float(diarios["relative_humidity_2m_mean"][i]),
                "velocidad_viento": float(diarios["windspeed_10m_max"][i] or 0),
            }
        )
    return salida


def _a_formato_siembra(respuesta: dict, dias: int) -> list[dict]:
    return [
        {
            "fecha": d["fecha"],
            "temp_max": d["temperatura_max"],
            "temp_min": d["temperatura_min"],
            "lluvia_mm": d["lluvia_mm"],
            "humedad": int(round(d["humedad_relativa"])),
            "velocidad_viento": round(d["velocidad_viento"], 2),
        }
        for d in _a_formato_diario(respuesta, dias)
    ]


async def _pronostico_desde_proxy(
    latitud: float,
    longitud: float,
    altitud: float,
    dias_solicitados: int,
    formatear: Callable[[dict, int], list[dict]],
) -> list[dict]:
    dias = min(max(dias_solicitados, 1), _FORECAST_DIAS_MAX)
    proxy = obtener_proxy()
    datos = await proxy.consultar_forecast(
        latitud,
        longitud,
        altitud,
        forecast_days=_FORECAST_DIAS_MAX,
        variables_diarias=_VARIABLES_DIARIAS,
    )
    resultado = formatear(datos, _FORECAST_DIAS_MAX)
    return resultado[:dias]


async def obtener_pronostico(latitud: float, longitud: float, altitud: float, dias: int) -> list[dict]:
    return await _pronostico_desde_proxy(latitud, longitud, altitud, dias, _a_formato_diario)


async def obtener_pronostico_siembra(
    latitud: float, longitud: float, altitud: float, dias: int = 15
) -> list[dict]:
    return await _pronostico_desde_proxy(latitud, longitud, altitud, dias, _a_formato_siembra)


async def obtener_historico(
    latitud: float, longitud: float, altitud: float, fecha_inicio: str, fecha_fin: str
) -> list[dict]:
    proxy = obtener_proxy()
    datos = await proxy.consultar_archive(
        latitud,
        longitud,
        altitud,
        fecha_inicio,
        fecha_fin,
        variables_diarias=_VARIABLES_DIARIAS,
    )
    return _a_formato_diario(datos, dias=10000)
