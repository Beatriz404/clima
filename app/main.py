from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.base_datos import Base, engine, obtener_sesion
from app.configuracion import obtener_ajustes
from app.esquemas import (
    RecomendacionDia,
    EstadoIntegracionMarn,
    RespuestaAjustada,
    RespuestaMarnComplemento,
    RespuestaPronostico,
    RespuestaInsights,
    ResumenMarnApiV1,
    RespuestaSiembra,
    SolicitudClima,
)
from app.modelos import RecomendacionSiembra, RegistroClimatico
from app.services.analitica_agricola import (
    lluvia_por_mes,
    notificaciones_agricolas,
    region_microclima,
    riesgo_exceso_lluvia,
    riesgo_sequia,
)
from app.services.agricultura import evaluar_dia_siembra
from app.services.ajuste_ml import modelo_ajuste_global
from app.services.marn import obtener_complemento_marn
from app.services.marn_intermedio import generar_resumen_marn_api_v1
from app.services.open_meteo import obtener_historico, obtener_pronostico

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Clima Agricola El Salvador",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Nacional MARN (API pública documentada)",
            "description": (
                "Backend intermedio estable (`/api/v1/nacional/marn/resumen`). "
                "Resume enlaces del portal público MARN; no altera Open-Meteo ni /forecast."
            ),
        },
        {
            "name": "MARN complemento (opcional)",
            "description": "Reenvío configurable vía `MARN_COMPLEMENTO_URL` hacia cualquier JSON compatible.",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


def _dias_open_meteo(dias_solicitados: int) -> int:
    return min(dias_solicitados, 16)


@app.get("/")
async def inicio():
    archivo = frontend_path / "index.html"
    if archivo.exists():
        return FileResponse(str(archivo))
    return {"mensaje": "API de Clima Agricola activa"}


@app.post("/forecast", response_model=RespuestaPronostico)
async def forecast(entrada: SolicitudClima):
    dias_consulta = _dias_open_meteo(entrada.dias)
    dias = await obtener_pronostico(entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta)
    return {
        "ubicacion": {"latitud": entrada.latitud, "longitud": entrada.longitud, "altitud": entrada.altitud},
        "dias": dias,
    }


@app.post("/adjusted", response_model=RespuestaAjustada)
async def adjusted(entrada: SolicitudClima, sesion: Session = Depends(obtener_sesion)):
    dias_consulta = _dias_open_meteo(entrada.dias)
    pronostico = await obtener_pronostico(entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta)
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
        "ubicacion": {"latitud": entrada.latitud, "longitud": entrada.longitud, "altitud": entrada.altitud},
        "modelo": "Scikit-learn MLPRegressor (fallback heuristico)",
        "dias": salida,
    }


@app.post("/planting", response_model=RespuestaSiembra)
async def planting(entrada: SolicitudClima, sesion: Session = Depends(obtener_sesion)):
    dias_consulta = _dias_open_meteo(entrada.dias)
    pronostico = await obtener_pronostico(entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta)
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
        "ubicacion": {"latitud": entrada.latitud, "longitud": entrada.longitud, "altitud": entrada.altitud},
        "recomendaciones": recomendaciones,
    }


@app.post("/insights", response_model=RespuestaInsights)
async def insights(entrada: SolicitudClima):
    dias_consulta = _dias_open_meteo(entrada.dias)
    pronostico = await obtener_pronostico(entrada.latitud, entrada.longitud, entrada.altitud, dias_consulta)
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
        "ubicacion": {"latitud": entrada.latitud, "longitud": entrada.longitud, "altitud": entrada.altitud},
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


@app.get(
    "/api/v1/nacional/marn/resumen",
    response_model=ResumenMarnApiV1,
    tags=["Nacional MARN (API pública documentada)"],
    summary="Resumen informativo (portal MARN, extracción superficial)",
    description=(
        "Contrato JSON estable (`schema_version`). "
        "Modos: `portal` (lectura HTML pública), `demo` (MARN_INTERMEDIO_MODO=demo), "
        "`off`, `no_disponible`. "
        "Coordenadas solo contextualizan la consulta en el cliente."
    ),
)
async def api_v1_nacional_marn_resumen(
    latitud: float = Query(..., ge=13.0, le=14.5, description="Latitud (El Salvador)"),
    longitud: float = Query(..., ge=-90.3, le=-87.5, description="Longitud (El Salvador)"),
    altitud: float = Query(650.0, ge=0, le=3500, description="Altitud aproximada en metros"),
):
    return await generar_resumen_marn_api_v1(latitud, longitud, altitud)


@app.get("/marn/estado", response_model=EstadoIntegracionMarn, tags=["MARN complemento (opcional)"])
async def marn_estado():
    """Indica si la URL opcional de complemento MARN está definida (sin exponer secretos)."""
    url = (obtener_ajustes().marn_complemento_url or "").strip()
    return EstadoIntegracionMarn(marn_complemento_configurado=bool(url))


@app.post("/marn/complemento", response_model=RespuestaMarnComplemento, tags=["MARN complemento (opcional)"])
async def marn_complemento(entrada: SolicitudClima):
    """
    Datos adicionales de red nacional (vía URL configurable). No altera /forecast, /adjusted, /planting ni /insights.
    """
    return await obtener_complemento_marn(entrada.latitud, entrada.longitud, entrada.altitud)
