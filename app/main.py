import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.base_datos import Base, engine, obtener_sesion
from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import (
    buscar_por_nombre,
    ubicacion_desde_coordenadas,
    ubicacion_mas_cercana,
)
from app.esquemas import (
    EstadoIntegracionMarn,
    RecomendacionDia,
    RespuestaAjustada,
    RespuestaInsights,
    RespuestaPronostico,
    RespuestaPronosticoApi,
    RespuestaSiembra,
    RespuestaUbicaciones,
    ResumenMarnApiV1,
    SolicitudClima,
    UbicacionDisponible,
)
from app.modelos import PronosticoSiembra, RecomendacionSiembra, RegistroClimatico
from app.services.batch_pronostico import ejecutar_actualizacion_batch, ejecutar_batch_inicial
from app.data.ubicaciones_salvador import UBICACIONES_SALVADOR
from app.services.pronostico_servicio import (
    obtener_pronostico_garantizado,
    obtener_pronostico_para_api,
)
from app.services.agricultura import evaluar_dia_siembra
from app.services.ajuste_ml import modelo_ajuste_global
from app.services.analitica_agricola import (
    lluvia_por_mes,
    notificaciones_agricolas,
    region_microclima,
    riesgo_exceso_lluvia,
    riesgo_sequia,
)
from app.services.marn_intermedio import generar_resumen_marn_api_v1
from app.services.open_meteo import (
    LimiteOpenMeteoError,
    ProxyServicioNoDisponibleError,
    obtener_historico,
)
from app.routes.pronostico import router as pronostico_router
from app.routes.sistema import router as sistema_router
from app.services.open_meteo_proxy import cerrar_proxy, iniciar_proxy, obtener_proxy

ajustes = obtener_ajustes()
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, ajustes.log_level, logging.INFO))
    await iniciar_proxy()
    Base.metadata.create_all(bind=engine)
    if ajustes.batch_habilitado:
        await ejecutar_batch_inicial()
        scheduler.add_job(
            ejecutar_actualizacion_batch,
            "interval",
            minutes=ajustes.batch_intervalo_minutos,
            id="batch_pronosticos_siembra",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Scheduler batch activo cada %d minutos", ajustes.batch_intervalo_minutos)
    yield
    if scheduler.running:
        scheduler.shutdown()
    await cerrar_proxy()


app = FastAPI(
    title=ajustes.nombre_app,
    version="1.0.0",
    description="API con datos de Open-Meteo y resumen del portal MARN El Salvador",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Pronóstico pre-calculado",
            "description": "Lectura desde base de datos (batch programado; sin Open-Meteo en vivo en producción).",
        },
        {
            "name": "Nacional MARN (API pública documentada)",
            "description": "Resumen informativo del portal público MARN.",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ajustes.cors_origins if not (ajustes.es_produccion and "*" in ajustes.cors_origins) else ajustes.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

app.include_router(pronostico_router)
app.include_router(sistema_router)


def _dias_open_meteo(dias_solicitados: int) -> int:
    return min(dias_solicitados, 16)


def _validar_coordenadas(latitud: float, longitud: float, altitud: float) -> None:
    if not ajustes.validate_coordinates(latitud, longitud, altitud):
        raise HTTPException(status_code=422, detail="Coordenadas fuera del territorio de El Salvador")


def _manejar_error_open_meteo(exc: Exception, contexto: str) -> HTTPException:
    if isinstance(exc, ProxyServicioNoDisponibleError):
        return HTTPException(
            status_code=503,
            detail=str(exc) or "Servicio de clima temporalmente no disponible. Intente en unos segundos.",
        )
    if isinstance(exc, LimiteOpenMeteoError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return HTTPException(
            status_code=429,
            detail="Límite de consultas a Open-Meteo alcanzado. Espere 1–2 minutos e intente de nuevo.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(status_code=502, detail=f"Error al consultar Open-Meteo: {exc}")
    return HTTPException(status_code=503, detail=f"{contexto}: {exc}")


def _resolver_ubicacion(
    ubicacion: str | None,
    latitud: float | None,
    longitud: float | None,
    altitud: float | None = None,
):
    if ubicacion:
        encontrada = buscar_por_nombre(ubicacion)
        if not encontrada:
            raise HTTPException(
                status_code=404,
                detail=f"Ubicación '{ubicacion}' no encontrada. Use GET /api/ubicaciones",
            )
        return encontrada
    if latitud is not None and longitud is not None:
        alt = 650.0 if altitud is None else altitud
        if not ajustes.validate_coordinates(latitud, longitud, alt):
            raise HTTPException(status_code=422, detail="Coordenadas fuera del territorio de El Salvador")
        return ubicacion_desde_coordenadas(latitud, longitud, alt)
    raise HTTPException(
        status_code=400,
        detail="Indique ubicacion=... o latitud=... y longitud=...",
    )


@app.get("/health")
async def health():
    """Estado del servicio y caché Open-Meteo."""
    try:
        proxy = obtener_proxy()
        stats = proxy.estadisticas_cache()
        return {
            "estado": "ok",
            "fuente_datos": "Open-Meteo (api.open-meteo.com)",
            "cache": "memoria",
            "pronostico_solo_batch": ajustes.pronostico_solo_batch,
            "batch_habilitado": ajustes.batch_habilitado,
            **stats,
        }
    except RuntimeError:
        return {"estado": "iniciando"}


@app.get("/api/ubicaciones", response_model=RespuestaUbicaciones, tags=["Pronóstico pre-calculado"])
async def api_ubicaciones():
    lista = [
        UbicacionDisponible(
            nombre=u.nombre,
            latitud=u.latitud,
            longitud=u.longitud,
            altitud=u.altitud,
            region=u.region,
        )
        for u in UBICACIONES_SALVADOR
    ]
    return RespuestaUbicaciones(total=len(lista), ubicaciones=lista)


@app.get("/api/pronostico", response_model=RespuestaPronosticoApi, tags=["Pronóstico pre-calculado"])
async def api_pronostico(
    ubicacion: str | None = Query(None, description="Nombre de la ciudad (ej. San Salvador)"),
    latitud: float | None = Query(None, ge=13.0, le=14.5),
    longitud: float | None = Query(None, ge=-90.3, le=-87.5),
    altitud: float | None = Query(None, ge=0, le=3500, description="Metros; obligatorio para parcela exacta en el mapa"),
    dias: int = Query(7, ge=1, le=15),
    sesion: Session = Depends(obtener_sesion),
):
    destino = _resolver_ubicacion(ubicacion, latitud, longitud, altitud)
    try:
        return await obtener_pronostico_garantizado(sesion, destino, dias)
    except LimiteOpenMeteoError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (httpx.HTTPStatusError, ValueError) as exc:
        raise _manejar_error_open_meteo(exc, f"Error al obtener pronóstico real para {destino.nombre}") from exc


@app.post("/api/admin/actualizar-pronosticos", tags=["Pronóstico pre-calculado"])
async def api_actualizar_pronosticos_manual():
    """Dispara el batch de inmediato (útil para pruebas)."""
    return await ejecutar_actualizacion_batch()


@app.get("/")
async def inicio():
    archivo = frontend_path / "index.html"
    if archivo.exists():
        return FileResponse(str(archivo))
    return {"mensaje": "API de Clima Agrícola activa"}


@app.post("/forecast", response_model=RespuestaPronostico)
async def forecast(entrada: SolicitudClima, sesion: Session = Depends(obtener_sesion)):
    _validar_coordenadas(entrada.latitud, entrada.longitud, entrada.altitud)
    try:
        dias_consulta = _dias_open_meteo(entrada.dias)
        dias = await obtener_pronostico_para_api(
            sesion, entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta
        )
        return {
            "ubicacion": {
                "latitud": entrada.latitud,
                "longitud": entrada.longitud,
                "altitud": entrada.altitud,
            },
            "dias": dias,
        }
    except (LimiteOpenMeteoError, httpx.HTTPStatusError) as exc:
        raise _manejar_error_open_meteo(exc, "Error al obtener pronóstico") from exc
    except Exception as exc:
        raise _manejar_error_open_meteo(exc, "Error al obtener pronóstico") from exc


@app.post("/adjusted", response_model=RespuestaAjustada)
async def adjusted(entrada: SolicitudClima, sesion: Session = Depends(obtener_sesion)):
    _validar_coordenadas(entrada.latitud, entrada.longitud, entrada.altitud)
    try:
        dias_consulta = _dias_open_meteo(entrada.dias)
        pronostico = await obtener_pronostico_para_api(
            sesion, entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta
        )
        salida = []
        for dia in pronostico:
            temperatura_media = (dia["temperatura_max"] + dia["temperatura_min"]) / 2
            ajuste = modelo_ajuste_global.ajustar(
                latitud=entrada.latitud,
                longitud=entrada.longitud,
                altitud=entrada.altitud,
                temperatura=temperatura_media,
                lluvia_mm=dia["lluvia_mm"],
                humedad_relativa=dia["humedad_relativa"],
                fecha=dia["fecha"],
            )
            salida.append(
                {
                    "fecha": dia["fecha"],
                    "temperatura_pronosticada": round(temperatura_media, 2),
                    "temperatura_ajustada": round(ajuste.temperatura_ajustada, 2),
                    "lluvia_pronosticada_mm": round(dia["lluvia_mm"], 2),
                    "probabilidad_lluvia_ajustada": round(ajuste.probabilidad_lluvia_ajustada, 3),
                    "humedad_relativa": round(dia["humedad_relativa"], 2),
                }
            )
            sesion.add(
                RegistroClimatico(
                    fecha=dia["fecha"],
                    latitud=entrada.latitud,
                    longitud=entrada.longitud,
                    altitud=entrada.altitud,
                    temperatura_pronosticada=temperatura_media,
                    lluvia_pronosticada_mm=dia["lluvia_mm"],
                    humedad_relativa=dia["humedad_relativa"],
                    temperatura_ajustada=ajuste.temperatura_ajustada,
                    probabilidad_lluvia_ajustada=ajuste.probabilidad_lluvia_ajustada,
                    creado_en=datetime.utcnow(),
                )
            )
        sesion.commit()
        return {
            "ubicacion": {
                "latitud": entrada.latitud,
                "longitud": entrada.longitud,
                "altitud": entrada.altitud,
            },
            "modelo": "Scikit-learn MLPRegressor",
            "dias": salida,
        }
    except HTTPException:
        sesion.rollback()
        raise
    except (LimiteOpenMeteoError, httpx.HTTPStatusError) as exc:
        sesion.rollback()
        raise _manejar_error_open_meteo(exc, "Error al procesar datos") from exc
    except Exception as exc:
        sesion.rollback()
        raise _manejar_error_open_meteo(exc, "Error al procesar datos") from exc


@app.post("/planting", response_model=RespuestaSiembra)
async def planting(entrada: SolicitudClima, sesion: Session = Depends(obtener_sesion)):
    _validar_coordenadas(entrada.latitud, entrada.longitud, entrada.altitud)
    try:
        dias_consulta = _dias_open_meteo(entrada.dias)
        pronostico = await obtener_pronostico_para_api(
            sesion, entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta
        )
        recomendaciones: list[RecomendacionDia] = []
        for dia in pronostico:
            temperatura_media = (dia["temperatura_max"] + dia["temperatura_min"]) / 2
            ajuste = modelo_ajuste_global.ajustar(
                latitud=entrada.latitud,
                longitud=entrada.longitud,
                altitud=entrada.altitud,
                temperatura=temperatura_media,
                lluvia_mm=dia["lluvia_mm"],
                humedad_relativa=dia["humedad_relativa"],
                fecha=dia["fecha"],
            )
            eval_siembra = evaluar_dia_siembra(
                temperatura_ajustada=ajuste.temperatura_ajustada,
                lluvia_mm=dia["lluvia_mm"],
                probabilidad_lluvia=ajuste.probabilidad_lluvia_ajustada,
            )
            recomendaciones.append(
                RecomendacionDia(
                    fecha=dia["fecha"],
                    apto_siembra=eval_siembra.apto_siembra,
                    puntaje=round(eval_siembra.puntaje, 2),
                    razon=eval_siembra.razon,
                )
            )
            sesion.add(
                RecomendacionSiembra(
                    fecha=dia["fecha"],
                    latitud=entrada.latitud,
                    longitud=entrada.longitud,
                    altitud=entrada.altitud,
                    apto_siembra=eval_siembra.apto_siembra,
                    puntaje=eval_siembra.puntaje,
                    razon=eval_siembra.razon,
                    creado_en=datetime.utcnow(),
                )
            )
        sesion.commit()
        return {
            "ubicacion": {
                "latitud": entrada.latitud,
                "longitud": entrada.longitud,
                "altitud": entrada.altitud,
            },
            "recomendaciones": recomendaciones,
        }
    except HTTPException:
        sesion.rollback()
        raise
    except (LimiteOpenMeteoError, httpx.HTTPStatusError) as exc:
        sesion.rollback()
        raise _manejar_error_open_meteo(exc, "Error al generar recomendaciones") from exc
    except Exception as exc:
        sesion.rollback()
        raise _manejar_error_open_meteo(exc, "Error al generar recomendaciones") from exc


@app.post("/insights", response_model=RespuestaInsights)
async def insights(entrada: SolicitudClima, sesion: Session = Depends(obtener_sesion)):
    _validar_coordenadas(entrada.latitud, entrada.longitud, entrada.altitud)
    try:
        dias_consulta = _dias_open_meteo(entrada.dias)
        pronostico = await obtener_pronostico_para_api(
            sesion, entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta
        )
        region = region_microclima(entrada.latitud, entrada.longitud, entrada.altitud)
        riesgo_sequia_data = riesgo_sequia(pronostico, region)
        riesgo_exceso_data = riesgo_exceso_lluvia(pronostico, region)
        recomendaciones = []
        temperaturas = []
        for dia in pronostico:
            temperatura_media = (dia["temperatura_max"] + dia["temperatura_min"]) / 2
            ajuste = modelo_ajuste_global.ajustar(
                latitud=entrada.latitud,
                longitud=entrada.longitud,
                altitud=entrada.altitud,
                temperatura=temperatura_media,
                lluvia_mm=dia["lluvia_mm"],
                humedad_relativa=dia["humedad_relativa"],
                fecha=dia["fecha"],
            )
            temperaturas.append({"fecha": dia["fecha"], "temperatura_c": round(ajuste.temperatura_ajustada, 2)})
            eval_siembra = evaluar_dia_siembra(
                temperatura_ajustada=ajuste.temperatura_ajustada,
                lluvia_mm=dia["lluvia_mm"],
                probabilidad_lluvia=ajuste.probabilidad_lluvia_ajustada,
            )
            recomendaciones.append({"fecha": dia["fecha"], "apto_siembra": eval_siembra.apto_siembra})

        hoy = date.today()
        inicio_actual = date(hoy.year, 1, 1).isoformat()
        fin_actual = hoy.isoformat()
        inicio_anterior = date(hoy.year - 1, 1, 1).isoformat()
        fin_anterior = date(hoy.year - 1, hoy.month, min(hoy.day, 28)).isoformat()
        historico_actual = await obtener_historico(entrada.latitud, entrada.longitud, entrada.altitud, inicio_actual, fin_actual)
        historico_anterior = await obtener_historico(
            entrada.latitud, entrada.longitud, entrada.altitud, inicio_anterior, fin_anterior
        )
        lluvia_actual = lluvia_por_mes(historico_actual)
        lluvia_anterior = lluvia_por_mes(historico_anterior)
        total_actual = sum(d["lluvia_mm"] for d in lluvia_actual)
        total_anterior = sum(d["lluvia_mm"] for d in lluvia_anterior)
        diferencia = total_actual - total_anterior
        variacion = (diferencia / total_anterior * 100) if total_anterior > 0 else 0.0
        avisos = notificaciones_agricolas(pronostico, riesgo_sequia_data, riesgo_exceso_data, recomendaciones)
        return {
            "ubicacion": {
                "latitud": entrada.latitud,
                "longitud": entrada.longitud,
                "altitud": entrada.altitud,
            },
            "region_microclima": region,
            "riesgo_sequia": riesgo_sequia_data,
            "riesgo_exceso_lluvia": riesgo_exceso_data,
            "temperatura_proximos_dias": temperaturas,
            "lluvia_mensual_actual": lluvia_actual,
            "lluvia_mensual_anterior": lluvia_anterior,
            "comparacion_anual": {
                "total_actual_mm": round(total_actual, 2),
                "total_anterior_mm": round(total_anterior, 2),
                "diferencia_mm": round(diferencia, 2),
                "variacion_porcentual": round(variacion, 2),
            },
            "notificaciones": avisos,
        }
    except HTTPException:
        raise
    except (LimiteOpenMeteoError, httpx.HTTPStatusError) as exc:
        raise _manejar_error_open_meteo(exc, "Error al generar insights") from exc
    except Exception as exc:
        raise _manejar_error_open_meteo(exc, "Error al generar insights") from exc


@app.get(
    "/api/v1/nacional/marn/resumen",
    response_model=ResumenMarnApiV1,
    tags=["Nacional MARN (API pública documentada)"],
    summary="Resumen informativo del portal MARN",
)
async def api_v1_nacional_marn_resumen(
    latitud: float = Query(..., ge=13.0, le=14.5),
    longitud: float = Query(..., ge=-90.3, le=-87.5),
    altitud: float = Query(650.0, ge=0, le=3500),
):
    _validar_coordenadas(latitud, longitud, altitud)
    return await generar_resumen_marn_api_v1(latitud, longitud, altitud)


@app.get("/marn/estado", response_model=EstadoIntegracionMarn)
async def marn_estado():
    url = str(ajustes.marn_complemento_url or "").strip()
    return EstadoIntegracionMarn(marn_complemento_configurado=bool(url))
