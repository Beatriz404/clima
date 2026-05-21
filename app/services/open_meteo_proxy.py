"""
Proxy asíncrono Open-Meteo: caché en memoria, deduplicación y control de concurrencia.

Datos siempre reales desde api.open-meteo.com. Sin Redis ni dependencias externas de caché.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any

import httpx

from app.configuracion import AjustesAplicacion, obtener_ajustes

logger = logging.getLogger(__name__)

_BACKOFF_429_SEGUNDOS = (1, 3, 7)
_FORECAST_DIAS_MAX = 15


class LimiteOpenMeteoError(Exception):
    """Open-Meteo respondió 429 tras agotar reintentos."""


class ProxyServicioNoDisponibleError(Exception):
    """Fallo al obtener datos del proxy."""


def _precision_cache(latitud: float, longitud: float, altitud: float) -> tuple[str, str, str]:
    """Clave de caché con precisión alta (~1 m); la API usa coordenadas exactas."""
    return f"{latitud:.6f}", f"{longitud:.6f}", f"{altitud:.1f}"


def clave_cache_forecast(latitud: float, longitud: float, altitud: float) -> str:
    lat, lon, alt = _precision_cache(latitud, longitud, altitud)
    return f"clima:forecast:{lat}:{lon}:{alt}"


def clave_cache_archive(
    latitud: float,
    longitud: float,
    altitud: float,
    fecha_inicio: str,
    fecha_fin: str,
) -> str:
    lat, lon, alt = _precision_cache(latitud, longitud, altitud)
    return f"clima:archive:{lat}:{lon}:{alt}:{fecha_inicio}:{fecha_fin}"


class OpenMeteoProxy:
    """
    Encapsula /v1/forecast y /v1/archive.

    - Caché TTL en memoria (forecast 30 min, archive 7 días)
    - Peticiones concurrentes idénticas comparten una sola llamada HTTP
    - Semáforo global + backoff ante 429
    """

    def __init__(self, ajustes: AjustesAplicacion | None = None) -> None:
        self.ajustes = ajustes or obtener_ajustes()
        self._cache: dict[str, tuple[float, dict]] = {}
        self._tareas_activas: dict[str, asyncio.Task[dict]] = {}
        self._mutex_cache = asyncio.Lock()
        self._cliente_http: httpx.AsyncClient | None = None
        self._semaforo = asyncio.Semaphore(self.ajustes.open_meteo_max_concurrent)

    async def iniciar(self) -> None:
        if self._cliente_http is not None and not self._cliente_http.is_closed:
            return
        await self.cerrar()
        limites = httpx.Limits(
            max_connections=self.ajustes.httpx_max_connections,
            max_keepalive_connections=self.ajustes.httpx_max_keepalive_connections,
        )
        self._cliente_http = httpx.AsyncClient(
            timeout=self.ajustes.timeout_conexion,
            limits=limites,
        )
        logger.info("Proxy Open-Meteo iniciado (caché en memoria, datos reales)")

    async def cerrar(self) -> None:
        for tarea in list(self._tareas_activas.values()):
            if not tarea.done():
                tarea.cancel()
        self._tareas_activas.clear()
        self._cache.clear()

        if self._cliente_http is not None:
            await self._cliente_http.aclose()
            self._cliente_http = None

    def limpiar_cache(self) -> None:
        self._cache.clear()

    def estadisticas_cache(self) -> dict[str, int]:
        ahora = monotonic()
        validas = sum(1 for expira, _ in self._cache.values() if expira > ahora)
        return {
            "entradas_validas": validas,
            "entradas_totales": len(self._cache),
            "peticiones_en_vuelo": len(self._tareas_activas),
        }

    async def _leer_cache(self, clave: str) -> dict | None:
        async with self._mutex_cache:
            entrada = self._cache.get(clave)
            if not entrada:
                return None
            expira, datos = entrada
            if monotonic() > expira:
                self._cache.pop(clave, None)
                return None
            return datos

    async def _escribir_cache(self, clave: str, datos: dict, ttl: int) -> None:
        async with self._mutex_cache:
            self._cache[clave] = (monotonic() + ttl, datos)

    async def _solicitar_json(self, url: str, parametros: dict[str, Any]) -> dict:
        if self._cliente_http is None:
            raise RuntimeError("Cliente HTTP del proxy no iniciado")

        async with self._semaforo:
            for intento, espera in enumerate(_BACKOFF_429_SEGUNDOS):
                respuesta = await self._cliente_http.get(url, params=parametros)
                if respuesta.status_code == 429:
                    if intento < len(_BACKOFF_429_SEGUNDOS) - 1:
                        logger.warning(
                            "Open-Meteo 429; reintento %d en %ds",
                            intento + 1,
                            espera,
                        )
                        await asyncio.sleep(espera)
                        continue
                    raise LimiteOpenMeteoError()
                respuesta.raise_for_status()
                return respuesta.json()

        raise LimiteOpenMeteoError()

    async def _obtener_con_cache(
        self,
        clave: str,
        ttl: int,
        obtener_remoto: Callable[[], Awaitable[dict]],
    ) -> dict:
        en_cache = await self._leer_cache(clave)
        if en_cache is not None:
            return en_cache

        tarea_existente = self._tareas_activas.get(clave)
        if tarea_existente is not None:
            try:
                return await tarea_existente
            except asyncio.CancelledError:
                self._tareas_activas.pop(clave, None)
                raise

        async def _cargar() -> dict:
            try:
                en_cache_local = await self._leer_cache(clave)
                if en_cache_local is not None:
                    return en_cache_local
                datos = await obtener_remoto()
                await self._escribir_cache(clave, datos, ttl)
                return datos
            finally:
                self._tareas_activas.pop(clave, None)

        tarea = asyncio.create_task(_cargar())
        self._tareas_activas[clave] = tarea
        try:
            return await tarea
        except Exception:
            if not tarea.done():
                tarea.cancel()
            raise

    async def consultar_forecast(
        self,
        latitud: float,
        longitud: float,
        altitud: float,
        *,
        forecast_days: int = _FORECAST_DIAS_MAX,
        variables_diarias: str,
    ) -> dict:
        clave = clave_cache_forecast(latitud, longitud, altitud)

        async def _fetch() -> dict:
            url = f"{self.ajustes.api_open_meteo_base}/forecast"
            parametros = {
                "latitude": latitud,
                "longitude": longitud,
                "elevation": altitud,
                "timezone": self.ajustes.zona_horaria,
                "daily": variables_diarias,
                "forecast_days": min(forecast_days, _FORECAST_DIAS_MAX),
            }
            return await self._solicitar_json(url, parametros)

        return await self._obtener_con_cache(clave, self.ajustes.cache_forecast_ttl, _fetch)

    async def consultar_archive(
        self,
        latitud: float,
        longitud: float,
        altitud: float,
        fecha_inicio: str,
        fecha_fin: str,
        *,
        variables_diarias: str,
    ) -> dict:
        clave = clave_cache_archive(latitud, longitud, altitud, fecha_inicio, fecha_fin)

        async def _fetch() -> dict:
            url = f"{self.ajustes.api_open_meteo_archivo_base}/archive"
            parametros = {
                "latitude": latitud,
                "longitude": longitud,
                "elevation": altitud,
                "timezone": self.ajustes.zona_horaria,
                "start_date": fecha_inicio,
                "end_date": fecha_fin,
                "daily": variables_diarias,
            }
            return await self._solicitar_json(url, parametros)

        return await self._obtener_con_cache(clave, self.ajustes.cache_archive_ttl, _fetch)


_proxy_global: OpenMeteoProxy | None = None


async def iniciar_proxy() -> None:
    global _proxy_global
    if _proxy_global is None:
        _proxy_global = OpenMeteoProxy()
    await _proxy_global.iniciar()


async def cerrar_proxy() -> None:
    global _proxy_global
    if _proxy_global is not None:
        await _proxy_global.cerrar()
        _proxy_global = None


def obtener_proxy() -> OpenMeteoProxy:
    if _proxy_global is None:
        raise RuntimeError(
            "Proxy Open-Meteo no inicializado. Arranque la app con el lifespan de FastAPI."
        )
    return _proxy_global


@asynccontextmanager
async def lifespan_proxy():
    await iniciar_proxy()
    try:
        yield
    finally:
        await cerrar_proxy()
