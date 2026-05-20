"""
Proxy asíncrono Open-Meteo con caché Redis y bloqueos distribuidos.

Elimina peticiones duplicadas concurrentes sobre las mismas coordenadas
y reduce errores HTTP 429 de la API pública.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from time import monotonic
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx
import redis.asyncio as aioredis

from app.configuracion import AjustesAplicacion, obtener_ajustes

logger = logging.getLogger(__name__)

_LIBERAR_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_BACKOFF_429_SEGUNDOS = (1, 3, 7)


class LimiteOpenMeteoError(Exception):
    """Open-Meteo respondió 429 tras agotar reintentos."""


class ProxyServicioNoDisponibleError(Exception):
    """Timeout o fallo al obtener datos vía proxy (caché / candado)."""


def redondear_coordenadas(latitud: float, longitud: float, altitud: float) -> tuple[float, float, int]:
    """Lat/lon a 3 decimales (~110 m); altitud a la decena más cercana."""
    return round(latitud, 3), round(longitud, 3), int(round(altitud, -1))


def clave_cache_forecast(latitud: float, longitud: float, altitud: float) -> str:
    lat, lon, alt = redondear_coordenadas(latitud, longitud, altitud)
    return f"clima:forecast:{lat:.3f}:{lon:.3f}:{alt}"


def clave_cache_archive(
    latitud: float,
    longitud: float,
    altitud: float,
    fecha_inicio: str,
    fecha_fin: str,
) -> str:
    lat, lon, alt = redondear_coordenadas(latitud, longitud, altitud)
    return f"clima:archive:{lat:.3f}:{lon:.3f}:{alt}:{fecha_inicio}:{fecha_fin}"


def clave_lock(cache_key: str) -> str:
    return f"lock:{cache_key}"


class AlmacenCache(Protocol):
    async def get(self, clave: str) -> str | None: ...
    async def set(self, clave: str, valor: str, ex: int) -> None: ...
    async def set_nx(self, clave: str, valor: str, ex: int) -> bool: ...
    async def eval_liberar_lock(self, clave_lock: str, token: str) -> None: ...
    async def cerrar(self) -> None: ...


class AlmacenRedis:
    def __init__(self, cliente: aioredis.Redis) -> None:
        self._redis = cliente

    async def get(self, clave: str) -> str | None:
        valor = await self._redis.get(clave)
        if valor is None:
            return None
        return valor.decode() if isinstance(valor, bytes) else str(valor)

    async def set(self, clave: str, valor: str, ex: int) -> None:
        await self._redis.set(clave, valor, ex=ex)

    async def set_nx(self, clave: str, valor: str, ex: int) -> bool:
        return bool(await self._redis.set(clave, valor, nx=True, ex=ex))

    async def eval_liberar_lock(self, clave_lock: str, token: str) -> None:
        await self._redis.eval(_LIBERAR_LOCK_LUA, 1, clave_lock, token)

    async def cerrar(self) -> None:
        await self._redis.aclose()


class AlmacenMemoria:
    """Backend en memoria para pruebas (REDIS_URL=memory://)."""

    def __init__(self) -> None:
        self._datos: dict[str, tuple[float, str]] = {}
        self._locks: dict[str, tuple[str, float]] = {}
        self._mutex = asyncio.Lock()

    async def get(self, clave: str) -> str | None:
        async with self._mutex:
            entrada = self._datos.get(clave)
            if not entrada:
                return None
            expira, valor = entrada
            if monotonic() > expira:
                self._datos.pop(clave, None)
                return None
            return valor

    async def set(self, clave: str, valor: str, ex: int) -> None:
        async with self._mutex:
            self._datos[clave] = (monotonic() + ex, valor)

    async def set_nx(self, clave: str, valor: str, ex: int) -> bool:
        async with self._mutex:
            ahora = monotonic()
            lock = self._locks.get(clave)
            if lock and lock[1] > ahora:
                return False
            self._locks[clave] = (valor, ahora + ex)
            return True

    async def eval_liberar_lock(self, clave_lock: str, token: str) -> None:
        async with self._mutex:
            lock = self._locks.get(clave_lock)
            if lock and lock[0] == token:
                self._locks.pop(clave_lock, None)

    async def cerrar(self) -> None:
        self._datos.clear()
        self._locks.clear()


class OpenMeteoProxy:
    """Encapsula /v1/forecast y /v1/archive con caché Redis y mutex distribuido."""

    def __init__(self, ajustes: AjustesAplicacion | None = None) -> None:
        self.ajustes = ajustes or obtener_ajustes()
        self._almacen: AlmacenCache | None = None
        self._cliente_http: httpx.AsyncClient | None = None
        self._semaforo = asyncio.Semaphore(self.ajustes.open_meteo_max_concurrent)

    async def iniciar(self) -> None:
        if (
            self._almacen is not None
            and self._cliente_http is not None
            and not self._cliente_http.is_closed
        ):
            return
        await self.cerrar()

        url = self.ajustes.redis_url.strip()
        if url == "memory://" or url == "memory":
            self._almacen = AlmacenMemoria()
            logger.info("Proxy Open-Meteo: almacén en memoria (pruebas/desarrollo)")
        else:
            cliente = aioredis.from_url(
                url,
                encoding="utf-8",
                decode_responses=False,
                socket_connect_timeout=5,
            )
            await cliente.ping()
            self._almacen = AlmacenRedis(cliente)
            logger.info("Proxy Open-Meteo: Redis conectado en %s", url.split("@")[-1])

        limites = httpx.Limits(
            max_connections=self.ajustes.httpx_max_connections,
            max_keepalive_connections=self.ajustes.httpx_max_keepalive_connections,
        )
        self._cliente_http = httpx.AsyncClient(
            timeout=self.ajustes.timeout_conexion,
            limits=limites,
        )

    async def cerrar(self) -> None:
        if self._cliente_http is not None:
            await self._cliente_http.aclose()
            self._cliente_http = None
        if self._almacen is not None:
            await self._almacen.cerrar()
            self._almacen = None

    def _requiere_iniciado(self) -> AlmacenCache:
        if self._almacen is None or self._cliente_http is None:
            raise RuntimeError("OpenMeteoProxy no iniciado; use iniciar_proxy() en el lifespan")
        return self._almacen

    async def _leer_cache(self, clave: str) -> dict | None:
        almacen = self._requiere_iniciado()
        crudo = await almacen.get(clave)
        if crudo is None:
            return None
        try:
            return json.loads(crudo)
        except json.JSONDecodeError:
            logger.warning("Entrada de caché corrupta, ignorando: %s", clave)
            return None

    async def _escribir_cache(self, clave: str, datos: dict, ttl: int) -> None:
        almacen = self._requiere_iniciado()
        await almacen.set(clave, json.dumps(datos, ensure_ascii=False), ex=ttl)

    async def _liberar_lock(self, clave_lock: str, token: str) -> None:
        almacen = self._requiere_iniciado()
        try:
            await almacen.eval_liberar_lock(clave_lock, token)
        except Exception:
            logger.exception("No se pudo liberar candado %s", clave_lock)

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
        clave_cache: str,
        ttl: int,
        obtener_remoto: Callable[[], Awaitable[dict]],
        reintento: int = 0,
    ) -> dict:
        almacen = self._requiere_iniciado()
        clave_lock = clave_lock_cache(clave_cache)

        en_cache = await self._leer_cache(clave_cache)
        if en_cache is not None:
            return en_cache

        token = secrets.token_hex(16)
        adquirio = await almacen.set_nx(clave_lock, token, ex=self.ajustes.redis_lock_ttl)

        if adquirio:
            try:
                en_cache = await self._leer_cache(clave_cache)
                if en_cache is not None:
                    return en_cache

                datos = await obtener_remoto()
                await self._escribir_cache(clave_cache, datos, ttl)
                return datos
            finally:
                await self._liberar_lock(clave_lock, token)

        limite = monotonic() + self.ajustes.redis_lock_espera_max
        while monotonic() < limite:
            await asyncio.sleep(self.ajustes.redis_lock_poll_interval)
            en_cache = await self._leer_cache(clave_cache)
            if en_cache is not None:
                return en_cache

        if reintento < 1:
            return await self._obtener_con_cache(
                clave_cache, ttl, obtener_remoto, reintento=reintento + 1
            )

        raise ProxyServicioNoDisponibleError(
            f"Timeout ({self.ajustes.redis_lock_espera_max}s) esperando datos en caché para {clave_cache}"
        )

    async def consultar_forecast(
        self,
        latitud: float,
        longitud: float,
        altitud: float,
        *,
        forecast_days: int = 15,
        variables_diarias: str,
    ) -> dict:
        clave = clave_cache_forecast(latitud, longitud, altitud)
        lat, lon, alt = redondear_coordenadas(latitud, longitud, altitud)

        async def _fetch() -> dict:
            url = f"{self.ajustes.api_open_meteo_base}/forecast"
            parametros = {
                "latitude": lat,
                "longitude": lon,
                "elevation": altitud,
                "timezone": self.ajustes.zona_horaria,
                "daily": variables_diarias,
                "forecast_days": forecast_days,
            }
            return await self._solicitar_json(url, parametros)

        return await self._obtener_con_cache(clave, self.ajustes.redis_forecast_ttl, _fetch)

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
        lat, lon, alt = redondear_coordenadas(latitud, longitud, altitud)

        async def _fetch() -> dict:
            url = f"{self.ajustes.api_open_meteo_archivo_base}/archive"
            parametros = {
                "latitude": lat,
                "longitude": lon,
                "elevation": altitud,
                "timezone": self.ajustes.zona_horaria,
                "start_date": fecha_inicio,
                "end_date": fecha_fin,
                "daily": variables_diarias,
            }
            return await self._solicitar_json(url, parametros)

        return await self._obtener_con_cache(clave, self.ajustes.redis_archive_ttl, _fetch)


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
