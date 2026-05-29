import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import (
    UbicacionSalvador,
    ubicacion_desde_coordenadas,
    ubicacion_mas_cercana,
)
from app.esquemas import DatoPronosticoSiembra, RespuestaPronosticoApi
from app.services.open_meteo import LimiteOpenMeteoError, obtener_pronostico, obtener_pronostico_siembra
from app.services.pronostico_repositorio import (
    FUENTE_OPEN_METEO,
    guardar_pronosticos_ubicacion,
    obtener_pronostico_db,
)

logger = logging.getLogger(__name__)

ORIGEN_CACHE = "base_datos"
ORIGEN_TIEMPO_REAL = "open_meteo_tiempo_real"
ORIGEN_CACHE_OBSOLETO = "base_datos_obsoleta"
ORIGEN_CIUDAD_REFERENCIA = "ciudad_referencia_batch"


def _es_parcela(ubicacion: UbicacionSalvador) -> bool:
    return ubicacion.nombre.startswith("Parcela (")


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
    return edad > timedelta(minutes=obtener_ajustes().pronostico_max_edad_minutos)


def _construir_respuesta(
    ubicacion: UbicacionSalvador,
    filas: list,
    ultima: datetime | None,
    origen: str,
    *,
    ubicacion_referencia: str | None = None,
    advertencia: str | None = None,
) -> RespuestaPronosticoApi:
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
    confiable = origen in (ORIGEN_CACHE, ORIGEN_TIEMPO_REAL, ORIGEN_CIUDAD_REFERENCIA)
    return RespuestaPronosticoApi(
        ubicacion=ubicacion.nombre,
        latitud=ubicacion.latitud,
        longitud=ubicacion.longitud,
        region=ubicacion.region,
        ultima_actualizacion=ultima,
        fuente=FUENTE_OPEN_METEO,
        datos_reales=True,
        confiable=confiable,
        origen=origen,
        ubicacion_referencia=ubicacion_referencia,
        advertencia=advertencia,
        dias=len(datos),
        datos=datos,
    )


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


async def _pronostico_parcela_desde_ciudad(
    sesion: Session,
    parcela: UbicacionSalvador,
    dias: int,
) -> RespuestaPronosticoApi:
    ciudad = ubicacion_mas_cercana(parcela.latitud, parcela.longitud)
    filas, ultima = obtener_pronostico_db(sesion, ciudad, dias)
    cfg = obtener_ajustes()
    if len(filas) < dias:
        raise ValueError(
            f"Aún no hay pronóstico batch para {ciudad.nombre}. "
            f"Espere {cfg.batch_intervalo_minutos} minutos tras el arranque."
        )
    obsoleto = _cache_obsoleto(ultima)
    origen = ORIGEN_CIUDAD_REFERENCIA if not obsoleto else ORIGEN_CACHE_OBSOLETO
    advertencia = (
        f"Pronóstico de referencia desde {ciudad.nombre} "
        f"(ciudad más cercana a su parcela; datos Open-Meteo actualizados cada "
        f"{cfg.batch_intervalo_minutos} min)."
    )
    if obsoleto and ultima:
        advertencia += (
            f" Última actualización: {ultima.isoformat()}. "
            "Se muestran los últimos datos disponibles."
        )
    return _construir_respuesta(
        parcela,
        filas,
        ultima,
        origen,
        ubicacion_referencia=ciudad.nombre,
        advertencia=advertencia,
    )


async def obtener_pronostico_garantizado(
    sesion: Session,
    ubicacion: UbicacionSalvador,
    dias: int,
) -> RespuestaPronosticoApi:
    """
    Devuelve pronóstico real Open-Meteo.

    Producción (pronostico_solo_batch): solo lectura desde BD del batch;
    parcelas usan la ciudad más cercana pre-calculada.
  """
    cfg = obtener_ajustes()
    if cfg.pronostico_solo_batch and _es_parcela(ubicacion):
        return await _pronostico_parcela_desde_ciudad(sesion, ubicacion, dias)

    filas, ultima = obtener_pronostico_db(sesion, ubicacion, dias)
    origen = ORIGEN_CACHE
    advertencia: str | None = None
    necesita_actualizar = len(filas) < dias or _cache_obsoleto(ultima)

    if necesita_actualizar and cfg.pronostico_solo_batch:
        if filas:
            advertencia = (
                "Datos en actualización automática. "
                f"Mostrando la última lectura guardada (cada {cfg.batch_intervalo_minutos} min)."
            )
            origen = ORIGEN_CACHE_OBSOLETO
        else:
            raise ValueError(
                f"No hay pronóstico guardado para {ubicacion.nombre}. "
                f"El sistema actualiza cada {cfg.batch_intervalo_minutos} min; intente en breve."
            )
    elif necesita_actualizar:
        try:
            await _sincronizar_desde_open_meteo(sesion, ubicacion, max(dias, 15))
            filas, ultima = obtener_pronostico_db(sesion, ubicacion, dias)
            origen = ORIGEN_TIEMPO_REAL
        except LimiteOpenMeteoError:
            if filas:
                advertencia = (
                    "Open-Meteo limitó consultas momentáneamente. "
                    "Mostrando el último pronóstico guardado (datos reales)."
                )
                origen = ORIGEN_CACHE_OBSOLETO
            else:
                raise
        except Exception as exc:
            if filas:
                logger.warning(
                    "Open-Meteo no disponible para %s; cache local. Error: %s",
                    ubicacion.nombre,
                    exc,
                )
                advertencia = "Servicio climático ocupado; mostrando último pronóstico guardado."
                origen = ORIGEN_CACHE_OBSOLETO
            else:
                raise

    if not filas:
        raise ValueError(f"No fue posible obtener pronóstico real para {ubicacion.nombre}")

    return _construir_respuesta(
        ubicacion,
        filas,
        ultima,
        origen,
        advertencia=advertencia,
    )


async def obtener_pronostico_para_api(
    sesion: Session,
    latitud: float,
    longitud: float,
    altitud: float,
    dias: int,
) -> list[dict]:
    """
    Punto único para endpoints legacy (/forecast, /adjusted, etc.).

    Con pronostico_solo_batch=True solo lee BD (vía obtener_pronostico_garantizado).
    En desarrollo puede consultar Open-Meteo en vivo a través del proxy.
    """
    cfg = obtener_ajustes()
    if cfg.pronostico_solo_batch:
        ubicacion = ubicacion_desde_coordenadas(latitud, longitud, altitud)
        respuesta = await obtener_pronostico_garantizado(sesion, ubicacion, dias)
        return [
            {
                "fecha": d.fecha,
                "temperatura_max": d.temp_max,
                "temperatura_min": d.temp_min,
                "lluvia_mm": d.lluvia_mm,
                "humedad_relativa": float(d.humedad),
                "velocidad_viento": d.velocidad_viento,
            }
            for d in respuesta.datos
        ]
    registros = await obtener_pronostico(latitud, longitud, altitud, dias)
    return [
        {
            "fecha": d["fecha"],
            "temperatura_max": d["temperatura_max"],
            "temperatura_min": d["temperatura_min"],
            "lluvia_mm": d["lluvia_mm"],
            "humedad_relativa": d["humedad_relativa"],
            "velocidad_viento": d.get("velocidad_viento", 0.0),
        }
        for d in registros
    ]
