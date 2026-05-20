"""Pruebas del proxy Open-Meteo (caché en memoria y deduplicación)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.configuracion import AjustesAplicacion
from app.services.open_meteo_proxy import (
    OpenMeteoProxy,
    clave_cache_archive,
    clave_cache_forecast,
    redondear_coordenadas,
)


def test_redondear_coordenadas_tres_decimales_y_altitud_decena():
    lat, lon, alt = redondear_coordenadas(13.69294, -89.21819, 653)
    assert lat == 13.693
    assert lon == -89.218
    assert alt == 650


def test_clave_forecast_formato():
    clave = clave_cache_forecast(13.6929, -89.2182, 653)
    assert clave == "clima:forecast:13.693:-89.218:650"


def test_clave_archive_incluye_fechas():
    clave = clave_cache_archive(13.6929, -89.2182, 650, "2024-01-01", "2024-01-31")
    assert clave == "clima:archive:13.693:-89.218:650:2024-01-01:2024-01-31"


@pytest.fixture
async def proxy():
    instancia = OpenMeteoProxy(AjustesAplicacion())
    await instancia.iniciar()
    yield instancia
    await instancia.cerrar()


@pytest.mark.asyncio
async def test_cache_hit_evita_segunda_llamada_http(proxy):
    respuesta = {
        "daily": {
            "time": ["2024-06-01"],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [20.0],
            "precipitation_sum": [1.0],
            "relative_humidity_2m_mean": [60.0],
            "windspeed_10m_max": [10.0],
        }
    }
    mock_get = AsyncMock(return_value=_respuesta_http(200, respuesta))

    with patch.object(proxy._cliente_http, "get", mock_get):
        r1 = await proxy.consultar_forecast(
            13.6929, -89.2182, 650, variables_diarias="temperature_2m_max"
        )
        r2 = await proxy.consultar_forecast(
            13.69296, -89.21821, 653, variables_diarias="temperature_2m_max"
        )

    assert r1 == r2
    assert mock_get.await_count == 1


@pytest.mark.asyncio
async def test_solicitudes_concurrentes_comparten_un_fetch(proxy):
    respuesta = {
        "daily": {
            "time": ["2024-06-01"],
            "temperature_2m_max": [28.0],
            "temperature_2m_min": [18.0],
            "precipitation_sum": [0.0],
            "relative_humidity_2m_mean": [55.0],
            "windspeed_10m_max": [8.0],
        }
    }
    llamadas = 0

    async def get_lento(*args, **kwargs):
        nonlocal llamadas
        llamadas += 1
        await asyncio.sleep(0.2)
        return _respuesta_http(200, respuesta)

    with patch.object(proxy._cliente_http, "get", side_effect=get_lento):
        resultados = await asyncio.gather(
            proxy.consultar_forecast(13.7, -89.2, 650, variables_diarias="temperature_2m_max"),
            proxy.consultar_forecast(13.7001, -89.2001, 652, variables_diarias="temperature_2m_max"),
            proxy.consultar_forecast(13.6999, -89.1999, 648, variables_diarias="temperature_2m_max"),
        )

    assert len(resultados) == 3
    assert llamadas == 1


@pytest.mark.asyncio
async def test_ttl_forecast_y_archive(proxy):
    assert proxy.ajustes.cache_archive_ttl == 604800
    assert proxy.ajustes.cache_forecast_ttl == 1800


def _respuesta_http(status: int, json_data: dict):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock
