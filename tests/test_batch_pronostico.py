"""Pruebas del sistema de pre-cálculo y API de pronósticos."""

from datetime import date, datetime

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
    return TestClient(app)


def test_catorce_ubicaciones_configuradas():
    assert len(UBICACIONES_SALVADOR) == 14
    assert buscar_por_nombre("San Salvador") is not None
    assert buscar_por_nombre("san salvador") is not None
    assert buscar_por_nombre("Usulutan") is not None


def test_ubicacion_mas_cercana_san_salvador():
    cerca = ubicacion_mas_cercana(13.6929, -89.2182)
    assert cerca.nombre == "San Salvador"


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
            "fecha": date.today(),
            "temp_max": 32.0,
            "temp_min": 22.0,
            "lluvia_mm": 1.5,
            "humedad": 65,
            "velocidad_viento": 10.2,
        }
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


@pytest.mark.asyncio
async def test_open_meteo_pronostico_siembra_real():
    from app.data.ubicaciones_salvador import buscar_por_nombre
    from app.services.open_meteo import obtener_pronostico_siembra

    ss = buscar_por_nombre("San Salvador")
    registros = await obtener_pronostico_siembra(ss.latitud, ss.longitud, ss.altitud, 7)
    assert len(registros) == 7
    hoy = registros[0]
    assert 15 <= hoy["temp_max"] <= 42
    assert 10 <= hoy["temp_min"] <= hoy["temp_max"]
    assert 0 <= hoy["humedad"] <= 100
