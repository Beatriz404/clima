import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import (
    UbicacionSalvador,
    es_ciudad_batch,
    ubicacion_desde_coordenadas,
    ubicacion_mas_cercana_con_distancia,
    ubicaciones_ordenadas_por_distancia,
)
from app.esquemas import DatoPronosticoSiembra, RespuestaPronosticoApi, RespuestaPronosticoParcela
from app.services.batch_pronostico import actualizar_ubicacion_en_batch
from app.services.pronostico_repositorio import (
    FUENTE_OPEN_METEO,
    obtener_pronostico_db,
    obtener_pronostico_db_reciente,
)

logger = logging.getLogger(__name__)

ORIGEN_CACHE = "base_datos"
ORIGEN_CACHE_OBSOLETO = "base_datos_obsoleta"
ORIGEN_CIUDAD_REFERENCIA = "ciudad_referencia_batch"


def _es_parcela(ubicacion: UbicacionSalvador) -> bool:
    if ubicacion.nombre.startswith("Parcela ("):
        return True
    return not es_ciudad_batch(ubicacion)


def _cache_obsoleto(ultima: datetime | None) -> bool:
    if ultima is None:
        return True
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    edad = datetime.now(timezone.utc) - ultima
    return edad > timedelta(minutes=obtener_ajustes().pronostico_max_edad_minutos)


def _leer_filas_batch(
    sesion: Session,
    ciudad: UbicacionSalvador,
    dias: int,
) -> tuple[list, datetime | None]:
    filas, ultima = obtener_pronostico_db(sesion, ciudad, dias)
    if len(filas) < dias:
        recientes, ultima_reciente = obtener_pronostico_db_reciente(sesion, ciudad, dias)
        if len(recientes) > len(filas):
            filas, ultima = recientes, ultima_reciente
    return filas, ultima


async def _rellenar_ciudad_desde_open_meteo(ciudad: UbicacionSalvador) -> bool:
    try:
        return await actualizar_ubicacion_en_batch(ciudad)
    except Exception as exc:
        logger.warning("No se pudo rellenar batch para %s: %s", ciudad.nombre, exc)
        return False


async def _obtener_datos_ciudad_referencia(
    sesion: Session,
    latitud: float,
    longitud: float,
    dias: int,
    *,
    ciudad_preferida: UbicacionSalvador | None = None,
) -> tuple[UbicacionSalvador, list, datetime | None, float]:
    """
    Devuelve datos reales Open-Meteo ya guardados en SQLite.
    Prueba la ciudad preferida y luego el resto por distancia; rellena una ciudad si falta.
    """
    orden = ubicaciones_ordenadas_por_distancia(latitud, longitud)
    if ciudad_preferida:
        dist_pref = next((d for u, d in orden if u.nombre == ciudad_preferida.nombre), 0.0)
        orden = [(ciudad_preferida, dist_pref)] + [
            par for par in orden if par[0].nombre != ciudad_preferida.nombre
        ]

    for ciudad, distancia_km in orden:
        filas, ultima = _leer_filas_batch(sesion, ciudad, dias)
        if not filas:
            if await _rellenar_ciudad_desde_open_meteo(ciudad):
                filas, ultima = _leer_filas_batch(sesion, ciudad, dias)
        if filas:
            return ciudad, filas, ultima, distancia_km

    logger.error("Sin datos batch tras intentar las %d ciudades", len(orden))
    return orden[0][0], [], None, orden[0][1]


def _construir_respuesta(
    ubicacion: UbicacionSalvador,
    filas: list,
    ultima: datetime | None,
    origen: str,
    *,
    ubicacion_referencia: str | None = None,
    advertencia: str | None = None,
    confiable: bool | None = None,
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
    if confiable is None:
        confiable = bool(filas) and origen in (ORIGEN_CACHE, ORIGEN_CIUDAD_REFERENCIA) and not _cache_obsoleto(ultima)
    return RespuestaPronosticoApi(
        ubicacion=ubicacion.nombre,
        latitud=ubicacion.latitud,
        longitud=ubicacion.longitud,
        region=ubicacion.region,
        ultima_actualizacion=ultima,
        fuente=FUENTE_OPEN_METEO,
        datos_reales=bool(filas),
        confiable=confiable,
        origen=origen,
        ubicacion_referencia=ubicacion_referencia,
        advertencia=advertencia,
        dias=len(datos),
        datos=datos,
    )


def _respuesta_desde_filas(
    ubicacion: UbicacionSalvador,
    ciudad: UbicacionSalvador,
    filas: list,
    ultima: datetime | None,
    dias: int,
    *,
    distancia_km: float | None = None,
) -> RespuestaPronosticoApi:
    cfg = obtener_ajustes()
    obsoleto = _cache_obsoleto(ultima)
    es_referencia = ciudad.nombre != ubicacion.nombre or distancia_km is not None

    origen = ORIGEN_CIUDAD_REFERENCIA if es_referencia and not obsoleto else ORIGEN_CACHE
    if obsoleto:
        origen = ORIGEN_CACHE_OBSOLETO

    advertencia = None
    if es_referencia and distancia_km is not None:
        advertencia = (
            f"Datos reales de {ciudad.nombre} (a {distancia_km:.1f} km de su parcela). "
            f"Actualización automática cada {cfg.batch_intervalo_minutos} min."
        )
    elif len(filas) < dias:
        advertencia = (
            f"Mostrando {len(filas)} de {dias} días disponibles para {ciudad.nombre}."
        )
    if obsoleto and ultima:
        advertencia = (advertencia or "") + " Última lectura guardada en base de datos."

    return _construir_respuesta(
        ubicacion,
        filas,
        ultima,
        origen,
        ubicacion_referencia=ciudad.nombre if es_referencia else None,
        advertencia=advertencia,
    )


async def _pronostico_parcela_desde_ciudad(
    sesion: Session,
    parcela: UbicacionSalvador,
    dias: int,
) -> RespuestaPronosticoApi:
    ciudad, filas, ultima, distancia_km = await _obtener_datos_ciudad_referencia(
        sesion, parcela.latitud, parcela.longitud, dias
    )
    return _respuesta_desde_filas(parcela, ciudad, filas, ultima, dias, distancia_km=distancia_km)


def _respuesta_parcela_desde_api(
    parcela: UbicacionSalvador,
    base: RespuestaPronosticoApi,
    ciudad_nombre: str,
    distancia_km: float,
) -> RespuestaPronosticoParcela:
    advertencia = base.advertencia or (
        f"Datos reales de {ciudad_nombre} (a {distancia_km:.1f} km)"
    )
    return RespuestaPronosticoParcela(
        latitud=parcela.latitud,
        longitud=parcela.longitud,
        altitud=parcela.altitud,
        ubicacion=parcela.nombre,
        region=parcela.region,
        ubicacion_referencia=ciudad_nombre,
        distancia_km=round(distancia_km, 1),
        advertencia=advertencia,
        ultima_actualizacion=base.ultima_actualizacion,
        fuente=base.fuente,
        datos_reales=base.datos_reales,
        confiable=base.confiable,
        origen=base.origen,
        dias=base.dias,
        pronostico=base.datos,
    )


async def obtener_pronostico_parcela(
    sesion: Session,
    latitud: float,
    longitud: float,
    altitud: float,
    dias: int,
) -> RespuestaPronosticoParcela:
    parcela = ubicacion_desde_coordenadas(latitud, longitud, altitud)
    base = await _pronostico_parcela_desde_ciudad(sesion, parcela, dias)
    ciudad, distancia_km = ubicacion_mas_cercana_con_distancia(parcela.latitud, parcela.longitud)
    ref = base.ubicacion_referencia or ciudad.nombre
    dist = distancia_km
    if base.ubicacion_referencia and base.ubicacion_referencia != ciudad.nombre:
        for c, d in ubicaciones_ordenadas_por_distancia(parcela.latitud, parcela.longitud):
            if c.nombre == base.ubicacion_referencia:
                dist = d
                break
    return _respuesta_parcela_desde_api(parcela, base, ref, dist)


async def obtener_pronostico_garantizado(
    sesion: Session,
    ubicacion: UbicacionSalvador,
    dias: int,
) -> RespuestaPronosticoApi:
    if _es_parcela(ubicacion):
        return await _pronostico_parcela_desde_ciudad(sesion, ubicacion, dias)

    ciudad, filas, ultima, distancia_km = await _obtener_datos_ciudad_referencia(
        sesion,
        ubicacion.latitud,
        ubicacion.longitud,
        dias,
        ciudad_preferida=ubicacion,
    )
    ref_km = distancia_km if ciudad.nombre != ubicacion.nombre else None
    return _respuesta_desde_filas(ubicacion, ciudad, filas, ultima, dias, distancia_km=ref_km)


async def obtener_pronostico_para_api(
    sesion: Session,
    latitud: float,
    longitud: float,
    altitud: float,
    dias: int,
) -> list[dict]:
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
