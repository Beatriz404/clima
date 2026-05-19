import asyncio
import logging
from datetime import datetime

from app.base_datos import SesionLocal
from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import UBICACIONES_SALVADOR
from app.services.open_meteo import obtener_pronostico_siembra
from app.services.pronostico_repositorio import guardar_pronosticos_ubicacion

logger = logging.getLogger(__name__)
ajustes = obtener_ajustes()

REINTENTOS = 3
ESPERA_REINTENTO_SEG = 2
PAUSA_ENTRE_UBICACIONES_SEG = 1.5
DIAS_PRONOSTICO = 15


async def _actualizar_ubicacion(ubicacion) -> bool:
    for intento in range(1, REINTENTOS + 1):
        try:
            registros = await obtener_pronostico_siembra(
                ubicacion.latitud,
                ubicacion.longitud,
                ubicacion.altitud,
                DIAS_PRONOSTICO,
            )
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
    resumen = {
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "duracion_segundos": (fin - inicio).total_seconds(),
        "ubicaciones_exitosas": exitosas,
        "ubicaciones_fallidas": fallidas,
        "total_ubicaciones": len(UBICACIONES_SALVADOR),
    }
    logger.info("[%s] Batch finalizado: %s", fin.isoformat(), resumen)
    return resumen
