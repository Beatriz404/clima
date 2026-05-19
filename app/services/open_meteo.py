import asyncio
from datetime import datetime
from time import monotonic

import httpx

from app.configuracion import obtener_ajustes

ajustes = obtener_ajustes()

_cache: dict[str, tuple[float, list[dict]]] = {}
_cliente_http: httpx.AsyncClient | None = None


class LimiteOpenMeteoError(Exception):
    """Open-Meteo respondió 429 tras agotar reintentos."""

    def __init__(
        self,
        mensaje: str = (
            "Límite de consultas a Open-Meteo alcanzado. "
            "Espere 1–2 minutos y vuelva a intentar."
        ),
    ):
        super().__init__(mensaje)


def limpiar_cache() -> None:
    _cache.clear()


def _clave_cache(tipo: str, latitud: float, longitud: float, altitud: float, **extra: object) -> str:
    partes = [tipo, f"{latitud:.4f}", f"{longitud:.4f}", f"{altitud:.1f}"]
    partes.extend(f"{k}={v}" for k, v in sorted(extra.items()))
    return "|".join(partes)


def _obtener_de_cache(clave: str) -> list[dict] | None:
    entrada = _cache.get(clave)
    if not entrada:
        return None
    expira_en, datos = entrada
    if monotonic() > expira_en:
        _cache.pop(clave, None)
        return None
    return datos


def _guardar_en_cache(clave: str, datos: list[dict]) -> None:
    _cache[clave] = (monotonic() + ajustes.cache_ttl, datos)


async def _cliente() -> httpx.AsyncClient:
    global _cliente_http
    if _cliente_http is None or _cliente_http.is_closed:
        _cliente_http = httpx.AsyncClient(timeout=ajustes.timeout_conexion)
    return _cliente_http


async def _solicitar_json(url: str, parametros: dict) -> dict:
    cliente = await _cliente()
    max_reintentos = 3
    for intento in range(max_reintentos):
        respuesta = await cliente.get(url, params=parametros)
        if respuesta.status_code == 429:
            if intento < max_reintentos - 1:
                await asyncio.sleep(2**intento + 1)
                continue
            raise LimiteOpenMeteoError()
        respuesta.raise_for_status()
        return respuesta.json()
    raise LimiteOpenMeteoError()


_VARIABLES_DIARIAS = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "relative_humidity_2m_mean,windspeed_10m_max"
)


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


async def obtener_pronostico(latitud: float, longitud: float, altitud: float, dias: int) -> list[dict]:
    clave = _clave_cache("forecast", latitud, longitud, altitud, dias=dias)
    en_cache = _obtener_de_cache(clave)
    if en_cache is not None:
        return en_cache

    url = f"{ajustes.api_open_meteo_base}/forecast"
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "elevation": altitud,
        "timezone": ajustes.zona_horaria,
        "daily": _VARIABLES_DIARIAS,
        "forecast_days": dias,
    }
    datos = await _solicitar_json(url, parametros)
    resultado = _a_formato_diario(datos, dias)
    _guardar_en_cache(clave, resultado)
    return resultado


async def obtener_pronostico_siembra(
    latitud: float, longitud: float, altitud: float, dias: int = 15
) -> list[dict]:
    """Pronóstico diario completo para persistencia en pronosticos_siembra."""
    clave = _clave_cache("forecast_siembra", latitud, longitud, altitud, dias=dias)
    en_cache = _obtener_de_cache(clave)
    if en_cache is not None:
        return en_cache

    url = f"{ajustes.api_open_meteo_base}/forecast"
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "elevation": altitud,
        "timezone": ajustes.zona_horaria,
        "daily": _VARIABLES_DIARIAS,
        "forecast_days": min(dias, 16),
    }
    datos = await _solicitar_json(url, parametros)
    resultado = _a_formato_siembra(datos, min(dias, 16))
    _guardar_en_cache(clave, resultado)
    return resultado


async def obtener_historico(
    latitud: float, longitud: float, altitud: float, fecha_inicio: str, fecha_fin: str
) -> list[dict]:
    clave = _clave_cache(
        "archive", latitud, longitud, altitud, inicio=fecha_inicio, fin=fecha_fin
    )
    en_cache = _obtener_de_cache(clave)
    if en_cache is not None:
        return en_cache

    url = f"{ajustes.api_open_meteo_archivo_base}/archive"
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "elevation": altitud,
        "timezone": ajustes.zona_horaria,
        "start_date": fecha_inicio,
        "end_date": fecha_fin,
        "daily": _VARIABLES_DIARIAS,
    }
    datos = await _solicitar_json(url, parametros)
    resultado = _a_formato_diario(datos, dias=10000)
    _guardar_en_cache(clave, resultado)
    return resultado
