"""
Backend intermedio: API pública estable que resume contenido del portal MARN (HTML público).

- No reemplaza Open-Meteo ni los endpoints /forecast, /adjusted, /planting, /insights.
- Extracción superficial (regex): enlaces y títulos relevantes; sin BeautifulSoup para mantener dependencias mínimas.
- Modos vía MARN_INTERMEDIO_MODO: auto | demo | off
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

import httpx

from app.configuracion import obtener_ajustes
from app.esquemas import ItemMarnExtraccion, ModoResumenMarn, ResumenMarnApiV1

NOTA_METODOLOGICA = (
    "Este endpoint es un agregador técnico independiente del MARN. "
    "En modo «portal» se descarga HTML público y se listan enlaces o textos detectados por palabras clave "
    "(meteorología, clima, lluvia, etc.); no valida contenido científico. "
    "Para alertas oficiales y datos normativos use los canales del Ministerio. "
    "Las coordenadas contextualizan la consulta en el cliente; la página consultada es la misma para todo el país."
)


def construir_url_portal(base: str, path: str) -> str:
    b = (base or "").strip()
    if not b:
        return ""
    p = (path or "").strip().lstrip("/")
    if not p:
        return b if b.endswith("/") else b + "/"
    if not b.endswith("/"):
        b = b + "/"
    return urljoin(b, p)


def extraer_items_de_portal_marn(html: str, base_url: str) -> list[ItemMarnExtraccion]:
    """Extrae enlaces potencialmente relacionados con meteorología desde HTML plano."""
    html_limpio = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html_limpio = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html_limpio)
    items: list[ItemMarnExtraccion] = []
    keywords = ("meteor", "clima", "lluvia", "pron", "tiempo", "ambiente", "calidad", "oleaje", "lluvias")
    for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]{3,200})</a>', html_limpio, re.I):
        href_raw, texto = m.group(1), unescape(m.group(2))
        texto = re.sub(r"\s+", " ", texto).strip()
        href = href_raw.strip()
        if not texto or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        comb = f"{href} {texto}".lower()
        if any(k in comb for k in keywords) or len(items) < 4:
            full = href if href.startswith("http") else urljoin(base_url, href)
            items.append(ItemMarnExtraccion(tipo="enlace", titulo=texto[:220], url=full[:2000]))
        if len(items) >= 14:
            break
    if not items:
        mt = re.search(r"<title[^>]*>([^<]{5,220})</title>", html_limpio, re.I)
        if mt:
            items.append(
                ItemMarnExtraccion(
                    tipo="texto",
                    titulo="Título del portal",
                    detalle=unescape(mt.group(1)).strip()[:500],
                )
            )
    return items[:14]


def _items_demo() -> list[ItemMarnExtraccion]:
    return [
        ItemMarnExtraccion(
            tipo="aviso",
            titulo="Modo demostración",
            detalle="MARN_INTERMEDIO_MODO=demo activo: sin llamadas HTTP al portal.",
        ),
        ItemMarnExtraccion(
            tipo="texto",
            titulo="Uso previsto",
            detalle="El front puede seguir usando Open-Meteo y llamar aparte a GET /api/v1/nacional/marn/resumen.",
        ),
    ]


async def _descargar_portal(url: str) -> str:
    headers = {
        "User-Agent": "ClimaAgricolaSV/1.0 (API intermedia documentada; +respetuoso scraping portal público)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-SV,es;q=0.9",
    }
    async with httpx.AsyncClient(timeout=18.0, follow_redirects=True) as cliente:
        resp = await cliente.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


async def generar_resumen_marn_api_v1(latitud: float, longitud: float, altitud: float) -> ResumenMarnApiV1:
    ajustes = obtener_ajustes()
    consulta = {"latitud": latitud, "longitud": longitud, "altitud": altitud}
    ahora = datetime.now(timezone.utc)
    modo_cfg = (ajustes.marn_intermedio_modo or "auto").strip().lower()

    if modo_cfg == "off":
        return ResumenMarnApiV1(
            generado_en=ahora,
            consulta=consulta,
            modo=ModoResumenMarn.off,
            url_portal_consultado=None,
            items=[],
            nota_metodologica=NOTA_METODOLOGICA
            + " Modo «off»: no se consultó la red (MARN_INTERMEDIO_MODO=off).",
        )

    if modo_cfg == "demo":
        return ResumenMarnApiV1(
            generado_en=ahora,
            consulta=consulta,
            modo=ModoResumenMarn.demo,
            url_portal_consultado=None,
            items=_items_demo(),
            nota_metodologica=NOTA_METODOLOGICA + " Modo «demo»: respuesta ilustrativa sin acceso al portal.",
        )

    url = construir_url_portal(ajustes.marn_portal_base_url, ajustes.marn_portal_path)
    if not url:
        return ResumenMarnApiV1(
            generado_en=ahora,
            consulta=consulta,
            modo=ModoResumenMarn.no_disponible,
            url_portal_consultado=None,
            items=[],
            nota_metodologica=NOTA_METODOLOGICA + " URL de portal vacía en configuración.",
        )

    try:
        html = await _descargar_portal(url)
        items = extraer_items_de_portal_marn(html, url)
        return ResumenMarnApiV1(
            generado_en=ahora,
            consulta=consulta,
            modo=ModoResumenMarn.portal,
            url_portal_consultado=url,
            items=items,
            nota_metodologica=NOTA_METODOLOGICA,
        )
    except Exception as exc:  # noqa: BLE001
        return ResumenMarnApiV1(
            generado_en=ahora,
            consulta=consulta,
            modo=ModoResumenMarn.no_disponible,
            url_portal_consultado=url,
            items=[
                ItemMarnExtraccion(
                    tipo="aviso",
                    titulo="No se pudo leer el portal",
                    detalle=str(exc)[:400],
                )
            ],
            nota_metodologica=NOTA_METODOLOGICA + " Falló la descarga o el análisis superficial del HTML.",
        )
