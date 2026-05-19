import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import UbicacionSalvador
from app.esquemas import DatoPronosticoSiembra, RespuestaPronosticoApi
from app.services.open_meteo import obtener_pronostico_siembra
from app.services.pronostico_repositorio import (
    FUENTE_OPEN_METEO,
    guardar_pronosticos_ubicacion,
    obtener_pronostico_db,
)

logger = logging.getLogger(__name__)
ajustes = obtener_ajustes()

ORIGEN_CACHE = "base_datos"
ORIGEN_TIEMPO_REAL = "open_meteo_tiempo_real"


def _validar_registro_real(registro: dict) -> bool:
    """Comprueba que los valores parecen mediciones reales de Open-Meteo."""
    try:
        temp_max = float(registro["temp_max"])
        temp_min = float(registro["temp_min"])
        lluvia = float(registro["lluvia_mm"])
        humedad = int(registro["humedad"])
        viento = float(registro["velocidad_viento"])
    except (KeyError, TypeError, ValueError):
        return False
    if not (-5 <= temp_min <= temp_max <= 48):
        return False
    if not (0 <= lluvia <= 600):
        return False
    if not (0 <= humedad <= 100):
        return False
    if not (0 <= viento <= 120):
        return False
    return True


def _cache_obsoleto(ultima: datetime | None) -> bool:
    if ultima is None:
        return True
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    edad = datetime.now(timezone.utc) - ultima
    return edad > timedelta(minutes=ajustes.pronostico_max_edad_minutos)


async def _sincronizar_desde_open_meteo(
    sesion: Session,
    ubicacion: UbicacionSalvador,
    dias: int,
) -> list[dict]:
    registros = await obtener_pronostico_siembra(
        ubicacion.latitud,
        ubicacion.longitud,
        ubicacion.altitud,
        dias,
    )
    if not registros or not all(_validar_registro_real(r) for r in registros):
        raise ValueError(f"Open-Meteo devolvió datos inválidos para {ubicacion.nombre}")
    guardar_pronosticos_ubicacion(sesion, ubicacion, registros)
    logger.info(
        "[%s] Pronóstico real Open-Meteo guardado: %s (%d días)",
        datetime.utcnow().isoformat(),
        ubicacion.nombre,
        len(registros),
    )
    return registros


async def obtener_pronostico_garantizado(
    sesion: Session,
    ubicacion: UbicacionSalvador,
    dias: int,
) -> RespuestaPronosticoApi:
    """
    Devuelve pronóstico real: primero desde BD; si falta o está obsoleto, consulta Open-Meteo.
    """
    filas, ultima = obtener_pronostico_db(sesion, ubicacion, dias)
    origen = ORIGEN_CACHE
    necesita_actualizar = len(filas) < dias or _cache_obsoleto(ultima)

    if necesita_actualizar:
        await _sincronizar_desde_open_meteo(sesion, ubicacion, max(dias, 15))
        filas, ultima = obtener_pronostico_db(sesion, ubicacion, dias)
        origen = ORIGEN_TIEMPO_REAL

    if not filas:
        raise ValueError(f"No fue posible obtener pronóstico real para {ubicacion.nombre}")

    datos = [
        DatoPronosticoSiembra(
            fecha=f.fecha_pronostico,
            temp_max=f.temp_max,
            temp_min=f.temp_min,
            lluvia_mm=f.lluvia_mm,
            humedad=f.humedad,
            velocidad_viento=f.velocidad_viento,
        )
        for f in filas
    ]

    return RespuestaPronosticoApi(
        ubicacion=ubicacion.nombre,
        latitud=ubicacion.latitud,
        longitud=ubicacion.longitud,
        region=ubicacion.region,
        ultima_actualizacion=ultima,
        fuente=FUENTE_OPEN_METEO,
        datos_reales=True,
        origen=origen,
        dias=len(datos),
        datos=datos,
    )
