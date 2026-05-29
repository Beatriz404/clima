"""Pruebas de consulta por coordenadas en cuadrícula estable."""

import pytest

from app.data.ubicaciones_salvador import (
    ubicacion_desde_coordenadas,
    ubicacion_mas_cercana,
)
from app.services.open_meteo_proxy import clave_cache_forecast


def test_ubicacion_desde_coordenadas_cuadricula_estable():
    lat, lon = 13.70512, -89.20187
    parcela = ubicacion_desde_coordenadas(lat, lon, 642.0)
    ciudad = ubicacion_mas_cercana(parcela.latitud, parcela.longitud)

    assert parcela.latitud == pytest.approx(13.7)
    assert parcela.longitud == pytest.approx(-89.2)
    assert parcela.altitud == 642.0
    assert parcela.nombre.startswith("Parcela (")
    assert parcela.latitud != ciudad.latitud or parcela.longitud != ciudad.longitud


def test_clave_cache_comparte_cuadricula():
    clave_a = clave_cache_forecast(13.69294, -89.21819, 653.2)
    clave_b = clave_cache_forecast(13.69296, -89.21821, 653.4)
    assert clave_a == clave_b
