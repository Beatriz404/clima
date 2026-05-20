"""Pruebas de integración: verificar que las APIs usan datos reales (sin demo ni mocks)."""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.configuracion import AjustesAplicacion, obtener_ajustes
from app.esquemas import ModoResumenMarn
from app.main import app
from app.services.marn_intermedio import generar_resumen_marn_api_v1
from app.services.open_meteo import obtener_pronostico
from app.services.srt_diarios import URL_SRT_DIARIOS, obtener_reporte_srt_diario, estacion_mas_cercana

FRONTEND_INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

PAYLOAD_SAN_SALVADOR = {
    "latitud": 13.6929,
    "longitud": -89.2182,
    "altitud": 650,
    "dias": 7,
}

COORDS_SANTA_ANA = {"latitud": 13.977, "longitud": -89.56, "altitud": 650}


@pytest.fixture
def cliente():
    with TestClient(app) as client:
        yield client


def test_configuracion_modo_auto_por_defecto():
    ajustes = obtener_ajustes()
    assert ajustes.marn_intermedio_modo == "auto"


def test_configuracion_demo_se_convierte_a_auto():
    ajustes = AjustesAplicacion(marn_intermedio_modo="demo")
    assert ajustes.marn_intermedio_modo == "auto"


def test_frontend_sin_datos_falsos():
    html = FRONTEND_INDEX.read_text(encoding="utf-8")
    prohibido = [
        "FORECAST_PATTERN",
        "mostrarDatosMARNMock",
        "recalculateForecastForLocation",
        "MODO DEMOSTRACIÓN",
        "datos ilustrativos",
    ]
    for texto in prohibido:
        assert texto not in html, f"El frontend aún contiene datos falsos o legacy: {texto}"
    assert "obtenerPronosticoReal" in html
    assert "obtenerMarnReal" in html
    assert 'fetch("/forecast"' in html


@pytest.fixture
async def proxy_iniciado():
    from app.services.open_meteo_proxy import iniciar_proxy

    await iniciar_proxy()


@pytest.mark.asyncio
async def test_open_meteo_pronostico_real(proxy_iniciado):
    dias = await obtener_pronostico(
        PAYLOAD_SAN_SALVADOR["latitud"],
        PAYLOAD_SAN_SALVADOR["longitud"],
        PAYLOAD_SAN_SALVADOR["altitud"],
        7,
    )
    assert len(dias) == 7
    for dia in dias:
        assert isinstance(dia["fecha"], date)
        assert -50 < dia["temperatura_max"] < 55
        assert -50 < dia["temperatura_min"] < 55
        assert dia["temperatura_max"] >= dia["temperatura_min"]
        assert 0 <= dia["lluvia_mm"] < 500
        assert 0 <= dia["humedad_relativa"] <= 100


def test_endpoint_forecast_real(cliente):
    respuesta = cliente.post("/forecast", json=PAYLOAD_SAN_SALVADOR)
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos.get("fuente") == "Open-Meteo"
    assert len(datos["dias"]) == 7
    assert "ubicacion" in datos
    primer = datos["dias"][0]
    assert "temperatura_max" in primer
    assert "lluvia_mm" in primer


def test_endpoint_adjusted_real(cliente):
    respuesta = cliente.post("/adjusted", json=PAYLOAD_SAN_SALVADOR)
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert len(datos["dias"]) == 7
    assert datos["modelo"]


def test_endpoint_planting_real(cliente):
    respuesta = cliente.post("/planting", json=PAYLOAD_SAN_SALVADOR)
    assert respuesta.status_code == 200, respuesta.text
    assert len(respuesta.json()["recomendaciones"]) == 7


@pytest.mark.asyncio
async def test_srt_reporte_diario_real():
    fecha, filas = await obtener_reporte_srt_diario()
    assert len(filas) >= 5, "SRT debe devolver estaciones del reporte diario"
    assert any(f.indice and f.nombre for f in filas)
    muestra = filas[0]
    assert muestra.lluvia_mm is not None or muestra.temp_max_dia_anterior_c is not None


@pytest.mark.asyncio
async def test_srt_estacion_cambia_con_ubicacion():
    fecha, filas = await obtener_reporte_srt_diario()
    ss = estacion_mas_cercana(13.6929, -89.2182, filas, fecha)
    sa = estacion_mas_cercana(13.977, -89.56, filas, fecha)
    assert ss is not None and sa is not None
    assert ss.nombre != sa.nombre or ss.indice != sa.indice


@pytest.mark.asyncio
async def test_marn_resumen_sin_modo_demo():
    resumen = await generar_resumen_marn_api_v1(
        PAYLOAD_SAN_SALVADOR["latitud"],
        PAYLOAD_SAN_SALVADOR["longitud"],
        PAYLOAD_SAN_SALVADOR["altitud"],
    )
    assert resumen.modo.value != "demo"
    assert resumen.modo in (
        ModoResumenMarn.portal,
        ModoResumenMarn.snet,
        ModoResumenMarn.no_disponible,
    )
    for item in resumen.items:
        assert "MODO DEMOSTRACIÓN" not in item.titulo.upper()
        assert "ilustrativ" not in (item.detalle or "").lower()


@pytest.mark.asyncio
async def test_marn_incluye_estacion_srt_real():
    resumen = await generar_resumen_marn_api_v1(
        PAYLOAD_SAN_SALVADOR["latitud"],
        PAYLOAD_SAN_SALVADOR["longitud"],
        PAYLOAD_SAN_SALVADOR["altitud"],
    )
    est = resumen.estacion_srt_cercana
    assert est is not None
    assert est.indice
    assert est.nombre
    assert resumen.url_datos_srt == URL_SRT_DIARIOS
    assert est.distancia_km is not None
    assert est.distancia_km < 50


def test_endpoint_marn_resumen_real(cliente):
    respuesta = cliente.get(
        "/api/v1/nacional/marn/resumen",
        params={
            "latitud": PAYLOAD_SAN_SALVADOR["latitud"],
            "longitud": PAYLOAD_SAN_SALVADOR["longitud"],
            "altitud": PAYLOAD_SAN_SALVADOR["altitud"],
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["modo"] != "demo"
    assert datos.get("estacion_srt_cercana") is not None
    est = datos["estacion_srt_cercana"]
    assert est["nombre"]
    assert est["indice"]


def test_marn_resumen_distinta_estacion_otra_ubicacion(cliente):
    r1 = cliente.get(
        "/api/v1/nacional/marn/resumen",
        params={
            "latitud": 13.6929,
            "longitud": -89.2182,
            "altitud": 650,
        },
    )
    r2 = cliente.get(
        "/api/v1/nacional/marn/resumen",
        params=COORDS_SANTA_ANA,
    )
    assert r1.status_code == 200 and r2.status_code == 200
    e1 = r1.json()["estacion_srt_cercana"]["nombre"]
    e2 = r2.json()["estacion_srt_cercana"]["nombre"]
    assert e1 != e2
