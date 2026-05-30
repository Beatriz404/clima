import asyncio
import logging
from datetime import datetime

from app.base_datos import SesionLocal
from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import UBICACIONES_SALVADOR
from app.services.batch_estado import registrar_ejecucion_batch
from app.services.open_meteo import LimiteOpenMeteoError, obtener_pronostico_siembra
from app.services.pronostico_repositorio import guardar_pronosticos_ubicacion

logger = logging.getLogger(__name__)

REINTENTOS = 3
ESPERA_REINTENTO_SEG = 3
PAUSA_ENTRE_UBICACIONES_SEG = 2.5
PAUSA_TRAS_429_SEG = 12
DIAS_PRONOSTICO = 15


async def actualizar_ubicacion_en_batch(ubicacion) -> bool:
    """Actualiza una ciudad del batch desde Open-Meteo (uso interno / relleno bajo demanda)."""
    return await _actualizar_ubicacion(ubicacion)


async def _actualizar_ubicacion(ubicacion) -> bool:
    for intento in range(1, REINTENTOS + 1):
        try:
            registros = await obtener_pronostico_siembra(
                ubicacion.latitud,
                ubicacion.longitud,
                ubicacion.altitud,
                DIAS_PRONOSTICO,
            )
            if not registros:
                raise ValueError("Open-Meteo devolvió lista vacía")
            sesion = SesionLocal()
            try:
                total = guardar_pronosticos_ubicacion(sesion, ubicacion, registros)
            finally:
                sesion.close()
            logger.info(
                "[%s] %s actualizada: %d días guardados",
                datetime.utcnow().isoformat(),
                ubicacion.nombre,
                total,
            )
            return True
        except LimiteOpenMeteoError as exc:
            logger.warning(
                "[%s] %s límite Open-Meteo (intento %d/%d)",
                datetime.utcnow().isoformat(),
                ubicacion.nombre,
                intento,
                REINTENTOS,
            )
            if intento < REINTENTOS:
                await asyncio.sleep(PAUSA_TRAS_429_SEG)
            elif intento == REINTENTOS:
                logger.error("[%s] %s: %s", datetime.utcnow().isoformat(), ubicacion.nombre, exc)
        except Exception as exc:
            logger.warning(
                "[%s] %s intento %d/%d falló: %s",
                datetime.utcnow().isoformat(),
                ubicacion.nombre,
                intento,
                REINTENTOS,
                exc,
            )
            if intento < REINTENTOS:
                await asyncio.sleep(ESPERA_REINTENTO_SEG)
    logger.error(
        "[%s] %s no se pudo actualizar tras %d reintentos",
        datetime.utcnow().isoformat(),
        ubicacion.nombre,
        REINTENTOS,
    )
    return False


async def ejecutar_actualizacion_batch() -> dict:
    inicio = datetime.utcnow()
    logger.info("[%s] Inicio batch pronósticos (%d ubicaciones)", inicio.isoformat(), len(UBICACIONES_SALVADOR))

    exitosas = 0
    fallidas = 0
    for ubicacion in UBICACIONES_SALVADOR:
        ok = await _actualizar_ubicacion(ubicacion)
        if ok:
            exitosas += 1
        else:
            fallidas += 1
        await asyncio.sleep(PAUSA_ENTRE_UBICACIONES_SEG)

    fin = datetime.utcnow()
    total = len(UBICACIONES_SALVADOR)
    resumen = {
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "duracion_segundos": (fin - inicio).total_seconds(),
        "ubicaciones_exitosas": exitosas,
        "ubicaciones_fallidas": fallidas,
        "total_ubicaciones": total,
        "exitosas": exitosas,
        "fallidas": fallidas,
        "total": total,
    }
    logger.info("[%s] Batch finalizado: %s", fin.isoformat(), resumen)
    registrar_ejecucion_batch(resumen)
    return resumen


async def ejecutar_batch_inicial() -> dict | None:
    """Batch al arrancar la app; no interrumpe el servicio si falla."""
    try:
        logger.info("Ejecutando batch inicial de pronósticos...")
        resultado = await ejecutar_actualizacion_batch()
        logger.info(
            "Batch inicial completado: %d/%d ubicaciones",
            resultado["exitosas"],
            resultado["total"],
        )
        return resultado
    except Exception as exc:
        logger.exception("Error en batch inicial (la aplicación continúa): %s", exc)
        return None
