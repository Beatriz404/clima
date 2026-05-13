import asyncio

from app.services.marn import obtener_complemento_marn


def test_marn_sin_url_devuelve_disponible_false(monkeypatch):
    class FakeAjustes:
        marn_complemento_url = None
        marn_api_token = None

    monkeypatch.setattr("app.services.marn.obtener_ajustes", lambda: FakeAjustes())

    salida = asyncio.run(obtener_complemento_marn(13.7, -89.2, 650.0))
    assert salida["disponible"] is False
    assert salida["datos"] is None
    assert "MARN" in salida["fuente"]
    assert salida["ubicacion"]["latitud"] == 13.7
