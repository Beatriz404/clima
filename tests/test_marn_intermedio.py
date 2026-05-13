from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.esquemas import ItemMarnExtraccion, ModoResumenMarn, ResumenMarnApiV1
from app.main import app
from app.services.marn_intermedio import extraer_items_de_portal_marn


def test_extraer_items_detecta_enlace_clima():
    html = """
    <html><head><title>MARN El Salvador</title></head><body>
    <a href="/ruta/pronostico-meteorologico/">Pronóstico meteorológico semanal</a>
    <a href="/otro/">Contacto</a>
    </body></html>
    """
    items = extraer_items_de_portal_marn(html, "https://www.marn.gob.sv/")
    assert len(items) >= 1
    assert any("meteor" in (i.titulo or "").lower() or (i.url and "pronostico" in i.url.lower()) for i in items)


def test_get_api_v1_marn_resumen_demo(monkeypatch):
    async def _fake(*_a, **_k):
        return ResumenMarnApiV1(
            generado_en=datetime.now(timezone.utc),
            consulta={"latitud": 13.7, "longitud": -89.2, "altitud": 650.0},
            modo=ModoResumenMarn.demo,
            items=[ItemMarnExtraccion(tipo="texto", titulo="Prueba", detalle="ok")],
            nota_metodologica="Nota de prueba.",
        )

    monkeypatch.setattr("app.main.generar_resumen_marn_api_v1", _fake)
    client = TestClient(app)
    r = client.get(
        "/api/v1/nacional/marn/resumen",
        params={"latitud": 13.7, "longitud": -89.2, "altitud": 650},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["modo"] == "demo"
    assert body["schema_version"] == "1.0"
    assert body["items"][0]["titulo"] == "Prueba"
