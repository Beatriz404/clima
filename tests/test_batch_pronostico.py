"""Pruebas del sistema de pre-cálculo y API de pronósticos."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data.ubicaciones_salvador import (
    UBICACIONES_SALVADOR,
    buscar_por_nombre,
    ubicacion_mas_cercana,
)
from app.main import app
from app.modelos import PronosticoSiembra
from app.services.pronostico_repositorio import guardar_pronosticos_ubicacion


@pytest.fixture
def cliente():
    with TestClient(app) as client:
        yield client


def test_catorce_ubicaciones_configuradas():
    assert len(UBICACIONES_SALVADOR) == 14
    assert buscar_por_nombre("San Salvador") is not None
    assert buscar_por_nombre("san salvador") is not None
    assert buscar_por_nombre("Usulutan") is not None


def test_ubicacion_mas_cercana_san_salvador():
    cerca = ubicacion_mas_cercana(13.6929, -89.2182)
    assert cerca.nombre == "San Salvador"


def test_api_sistema_estado(cliente):
    respuesta = cliente.get("/api/sistema/estado")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["ubicaciones_batch"] == 14
    assert "pronostico_solo_batch" in datos
    assert "proxy_cache" in datos
    assert datos["nota"]


def test_api_ubicaciones(cliente):
    respuesta = cliente.get("/api/ubicaciones")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["total"] == 14
    assert any(u["nombre"] == "Santa Ana" for u in datos["ubicaciones"])


def test_api_pronostico_desde_db(cliente):
    from app.base_datos import SesionLocal

    ubicacion = buscar_por_nombre("San Salvador")
    registros = [
        {
            "fecha": date.today() + timedelta(days=i),
            "temp_max": 32.0,
            "temp_min": 22.0,
            "lluvia_mm": 1.5,
            "humedad": 65,
            "velocidad_viento": 10.2,
        }
        for i in range(7)
    ]
    sesion = SesionLocal()
    try:
        guardar_pronosticos_ubicacion(sesion, ubicacion, registros)
    finally:
        sesion.close()

    respuesta = cliente.get("/api/pronostico", params={"ubicacion": "San Salvador", "dias": 7})
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["ubicacion"] == "San Salvador"
    assert datos["fuente"] == "Open-Meteo"
    assert datos["datos_reales"] is True
    assert len(datos["datos"]) >= 1
    assert datos["datos"][0]["temp_max"] == 32.0


def test_api_pronostico_parcela_usa_ciudad_referencia(cliente, monkeypatch):
    from app.base_datos import SesionLocal
    from app.configuracion import obtener_ajustes

    obtener_ajustes.cache_clear()
    monkeypatch.setenv("PRONOSTICO_SOLO_BATCH", "true")
    monkeypatch.setenv("ENTORNO", "testing")
    obtener_ajustes.cache_clear()

    ciudad = buscar_por_nombre("San Salvador")
    registros = [
        {
            "fecha": date.today(),
            "temp_max": 31.0,
            "temp_min": 21.0,
            "lluvia_mm": 2.0,
            "humedad": 70,
            "velocidad_viento": 8.0,
        }
    ]
    sesion = SesionLocal()
    try:
        guardar_pronosticos_ubicacion(sesion, ciudad, registros)
    finally:
        sesion.close()

    respuesta = cliente.get(
        "/api/pronostico",
        params={"latitud": 13.705, "longitud": -89.202, "altitud": 640, "dias": 1},
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["origen"] == "ciudad_referencia_batch"
    assert datos["ubicacion_referencia"] == "San Salvador"
    assert datos["confiable"] is True
    assert datos["advertencia"]
    obtener_ajustes.cache_clear()


@pytest.fixture
async def proxy_iniciado():
    from app.services.open_meteo_proxy import iniciar_proxy

    await iniciar_proxy()


@pytest.mark.asyncio
async def test_open_meteo_pronostico_siembra_real(proxy_iniciado):
    from app.data.ubicaciones_salvador import buscar_por_nombre
    from app.services.open_meteo import obtener_pronostico_siembra

    ss = buscar_por_nombre("San Salvador")
    registros = await obtener_pronostico_siembra(ss.latitud, ss.longitud, ss.altitud, 7)
    assert len(registros) == 7
    hoy = registros[0]
    assert 15 <= hoy["temp_max"] <= 42
    assert 10 <= hoy["temp_min"] <= hoy["temp_max"]
    assert 0 <= hoy["humedad"] <= 100
