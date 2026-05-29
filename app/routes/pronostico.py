"""Rutas de pronóstico (parcelas en mapa y monitoreo)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.base_datos import obtener_sesion
from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import UBICACIONES_SALVADOR
from app.esquemas import RespuestaPronosticoParcela
from app.services.batch_estado import obtener_ultima_ejecucion_batch
from app.services.open_meteo import LimiteOpenMeteoError
from app.services.open_meteo_proxy import obtener_proxy
from app.services.pronostico_servicio import obtener_pronostico_parcela

router = APIRouter(prefix="/api", tags=["Pronóstico pre-calculado"])


@router.get("/pronostico/parcela", response_model=RespuestaPronosticoParcela)
async def api_pronostico_parcela(
    latitud: float = Query(..., ge=13.0, le=14.5, alias="lat"),
    longitud: float = Query(..., ge=-90.3, le=-87.5, alias="lng"),
    altitud: float = Query(650.0, ge=0, le=3500),
    dias: int = Query(7, ge=1, le=15),
    sesion: Session = Depends(obtener_sesion),
):
    """
    Pronóstico para parcela en el mapa.

    Solo lee SQLite (batch de la ciudad más cercana). No llama Open-Meteo en vivo.
    """
    cfg = obtener_ajustes()
    if not cfg.validate_coordinates(latitud, longitud, altitud):
        raise HTTPException(status_code=422, detail="Coordenadas fuera de El Salvador")
    try:
        return await obtener_pronostico_parcela(sesion, latitud, longitud, altitud, dias)
    except LimiteOpenMeteoError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/sistema/estado")
async def api_sistema_estado():
    """Monitoreo: modo batch, última ejecución y caché del proxy."""
    cfg = obtener_ajustes()
    try:
        proxy_stats = obtener_proxy().estadisticas_cache()
    except RuntimeError:
        proxy_stats = {"error": "proxy_no_iniciado"}

    return {
        "modo_batch": cfg.pronostico_solo_batch,
        "pronostico_solo_batch": cfg.pronostico_solo_batch,
        "batch_habilitado": cfg.batch_habilitado,
        "batch_intervalo_minutos": cfg.batch_intervalo_minutos,
        "ultimo_batch": obtener_ultima_ejecucion_batch(),
        "ubicaciones_batch": len(UBICACIONES_SALVADOR),
        "cache_proxy": proxy_stats,
        "nota": "Parcelas del mapa usan solo SQLite (ciudad batch más cercana).",
    }
