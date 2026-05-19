import asyncio
from collections.abc import Callable
from datetime import datetime
from time import monotonic

import httpx

from app.configuracion import obtener_ajustes

ajustes = obtener_ajustes()

_cache: dict[str, tuple[float, list[dict]]] = {}
_solicitudes_activas: dict[str, asyncio.Task[list[dict]]] = {}
_semaphore_open_meteo = asyncio.Semaphore(2)
_cliente_http: httpx.AsyncClient | None = None

_FORECAST_DIAS_MAX = 15


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
    _solicitudes_activas.clear()


def _clave_cache(tipo: str, latitud: float, longitud: float, altitud: float, **extra: object) -> str:
    altitud_redondeada = round(altitud, -1)
    partes = [tipo, f"{latitud:.4f}", f"{longitud:.4f}", f"{altitud_redondeada:.0f}"]
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
    async with _semaphore_open_meteo:
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


async def _obtener_pronostico_dedup(
    clave: str,
    latitud: float,
    longitud: float,
    altitud: float,
    dias_solicitados: int,
    formatear: Callable[[dict, int], list[dict]],
) -> list[dict]:
    dias = min(max(dias_solicitados, 1), _FORECAST_DIAS_MAX)

    en_cache = _obtener_de_cache(clave)
    if en_cache is not None:
        return en_cache[:dias]

    if clave in _solicitudes_activas:
        resultado = await _solicitudes_activas[clave]
        return resultado[:dias]

    async def _cargar() -> list[dict]:
        url = f"{ajustes.api_open_meteo_base}/forecast"
        parametros = {
            "latitude": latitud,
            "longitude": longitud,
            "elevation": altitud,
            "timezone": ajustes.zona_horaria,
            "daily": _VARIABLES_DIARIAS,
            "forecast_days": _FORECAST_DIAS_MAX,
        }
        datos = await _solicitar_json(url, parametros)
        resultado = formatear(datos, _FORECAST_DIAS_MAX)
        _guardar_en_cache(clave, resultado)
        return resultado

    tarea = asyncio.create_task(_cargar())
    _solicitudes_activas[clave] = tarea
    try:
        resultado = await tarea
        return resultado[:dias]
    finally:
        _solicitudes_activas.pop(clave, None)


async def obtener_pronostico(latitud: float, longitud: float, altitud: float, dias: int) -> list[dict]:
    clave = _clave_cache("forecast", latitud, longitud, altitud)
    return await _obtener_pronostico_dedup(
        clave,
        latitud,
        longitud,
        altitud,
        dias,
        _a_formato_diario,
    )


async def obtener_pronostico_siembra(
    latitud: float, longitud: float, altitud: float, dias: int = 15
) -> list[dict]:
    """Pronóstico diario completo para persistencia en pronosticos_siembra."""
    clave = _clave_cache("forecast_siembra", latitud, longitud, altitud)
    return await _obtener_pronostico_dedup(
        clave,
        latitud,
        longitud,
        altitud,
        dias,
        _a_formato_siembra,
    )


async def obtener_historico(
    latitud: float, longitud: float, altitud: float, fecha_inicio: str, fecha_fin: str
) -> list[dict]:
    clave = _clave_cache(
        "archive", latitud, longitud, altitud, inicio=fecha_inicio, fin=fecha_fin
    )
    en_cache = _obtener_de_cache(clave)
    if en_cache is not None:
        return en_cache

    if clave in _solicitudes_activas:
        return await _solicitudes_activas[clave]

    async def _cargar() -> list[dict]:
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

    tarea = asyncio.create_task(_cargar())
    _solicitudes_activas[clave] = tarea
    try:
        return await tarea
    finally:
        _solicitudes_activas.pop(clave, None)
