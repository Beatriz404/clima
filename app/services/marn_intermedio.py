import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.configuracion import obtener_ajustes
from app.esquemas import ItemMarnExtraccion, ModoResumenMarn, ResumenMarnApiV1
from app.services.srt_diarios import URL_SRT_DIARIOS, obtener_estacion_srt_para_ubicacion

logger = logging.getLogger(__name__)
ajustes = obtener_ajustes()

_HEADERS_NAVEGADOR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-SV,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_URLS_MARN = (
    "https://www.marn.gob.sv/",
    "https://www.marn.gob.sv",
)

_URL_SNET_PRONOSTICO_48H = "https://www.snet.gob.sv/ver/meteorologia/pronostico/24+horas"
_URL_SNET_INFORMES = "https://www.snet.gob.sv/ver/riesgo/ultimos+informes+y+avisos/"
_URL_SNET_METEOROLOGIA = "https://snet.gob.sv/page.php?id=1"


def _aplicar_estacion_srt(resumen: ResumenMarnApiV1, estacion) -> ResumenMarnApiV1:
    if estacion is None:
        return resumen
    datos = resumen.model_dump()
    datos["estacion_srt_cercana"] = estacion
    datos["url_datos_srt"] = URL_SRT_DIARIOS
    partes = []
    if estacion.lluvia_mm is not None:
        partes.append(f"Lluvia: {estacion.lluvia_mm} mm")
    if estacion.temp_max_dia_anterior_c is not None:
        partes.append(f"T. max. dia anterior: {estacion.temp_max_dia_anterior_c} C")
    if estacion.temp_min_dia_actual_c is not None:
        partes.append(f"T. min. dia actual: {estacion.temp_min_dia_actual_c} C")
    if estacion.humedad_relativa_pct is not None:
        partes.append(f"Humedad: {estacion.humedad_relativa_pct}%")
    detalle_estacion = ", ".join(partes) if partes else "Reporte diario de red convencional MARN."
    dist_txt = (
        f" (~{estacion.distancia_km} km del punto seleccionado)"
        if estacion.distancia_km is not None
        else ""
    )
    item_estacion = ItemMarnExtraccion(
        tipo="estacion_srt",
        titulo=f"Estación cercana: {estacion.nombre} ({estacion.indice}){dist_txt}",
        detalle=detalle_estacion,
        url=URL_SRT_DIARIOS,
    )
    datos["items"] = [item_estacion, *datos["items"][:4]]
    nota_srt = (
        f"Datos diarios de red convencional (CCA/DGOA-MARN) para la estación más próxima al mapa. "
        f"Fuente: {URL_SRT_DIARIOS}"
    )
    if datos.get("nota_metodologica"):
        datos["nota_metodologica"] = datos["nota_metodologica"] + " " + nota_srt
    else:
        datos["nota_metodologica"] = nota_srt
    return ResumenMarnApiV1(**datos)

_PALABRAS_PRONOSTICO = (
    "lluvia",
    "lluvias",
    "temperatura",
    "viento",
    "cielo",
    "nublado",
    "humedad",
    "pronost",
    "mañana",
    "manana",
    "tarde",
    "noche",
    "onda tropical",
    "actividad eléctrica",
    "actividad electrica",
)


def _resumen_base(latitud: float, longitud: float, altitud: float) -> dict:
    return {
        "generado_en": datetime.now(),
        "consulta": {"latitud": latitud, "longitud": longitud, "altitud": altitud},
    }


def _items_enlaces_oficiales() -> list[ItemMarnExtraccion]:
    return [
        ItemMarnExtraccion(
            tipo="enlace",
            titulo="Pronóstico 48 horas (SNET / DGOA-MARN)",
            url=_URL_SNET_PRONOSTICO_48H,
            detalle="Perspectiva meteorológica oficial para El Salvador.",
        ),
        ItemMarnExtraccion(
            tipo="enlace",
            titulo="Informes y avisos de riesgo",
            url=_URL_SNET_INFORMES,
            detalle="Últimos boletines e informes del observatorio nacional.",
        ),
        ItemMarnExtraccion(
            tipo="enlace",
            titulo="Portal institucional del MARN",
            url=str(ajustes.marn_portal_base_url),
            detalle="Ministerio de Medio Ambiente y Recursos Naturales.",
        ),
        ItemMarnExtraccion(
            tipo="enlace",
            titulo="Sección de meteorología (SNET)",
            url=_URL_SNET_METEOROLOGIA,
            detalle="Productos y servicios meteorológicos del MARN.",
        ),
        ItemMarnExtraccion(
            tipo="enlace",
            titulo="Reporte diario de estaciones (SRT / CCA-MARN)",
            url=URL_SRT_DIARIOS,
            detalle="Red convencional: lluvia, temperaturas y humedad por estación.",
        ),
    ]


async def _obtener_html(cliente: httpx.AsyncClient, urls: tuple[str, ...]) -> tuple[str | None, str | None]:
    for url in urls:
        try:
            respuesta = await cliente.get(url)
            if respuesta.status_code == 200 and len(respuesta.text) > 500:
                return respuesta.text, str(respuesta.url)
            logger.info("MARN/SNET: %s respondió %s", url, respuesta.status_code)
        except Exception as exc:
            logger.warning("MARN/SNET: fallo al consultar %s: %s", url, exc)
    return None, None


def _es_texto_navegacion(texto: str) -> bool:
    lower = texto.lower()
    if len(texto) > 200 and sum(1 for p in _PALABRAS_PRONOSTICO if p in lower) >= 4:
        return True
    indicadores_menu = (
        "red automática",
        "red automatica",
        "lluvia acumulada",
        "lluvia registrada",
        "productos y servicios",
        "referencia territorial",
        "sección educativa",
    )
    return sum(1 for ind in indicadores_menu if ind in lower) >= 2


def _puntuar_texto_pronostico(texto: str) -> int:
    lower = texto.lower()
    puntaje = 0
    if lower.startswith(("en la mañana", "en la manana", "por la tarde", "por la noche", "el viento", "influencia")):
        puntaje += 10
    if any(p in lower for p in ("parcialmente nublado", "lluvias", "actividad eléctrica", "actividad electrica")):
        puntaje += 5
    if 60 <= len(texto) <= 320:
        puntaje += 3
    if _es_texto_navegacion(texto):
        puntaje -= 20
    return puntaje


def _extraer_items_desde_html(html: str, base_url: str) -> list[ItemMarnExtraccion]:
    soup = BeautifulSoup(html, "html.parser")
    candidatos: list[tuple[int, str]] = []
    vistos: set[str] = set()

    for parrafo in soup.find_all(["p", "li", "td"]):
        texto = parrafo.get_text(" ", strip=True)
        texto = re.sub(r"\s+", " ", texto)
        if len(texto) < 40 or len(texto) > 450:
            continue
        if not any(palabra in texto.lower() for palabra in _PALABRAS_PRONOSTICO):
            continue
        if _es_texto_navegacion(texto):
            continue
        clave = texto[:80].lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        candidatos.append((_puntuar_texto_pronostico(texto), texto))

    candidatos.sort(key=lambda par: par[0], reverse=True)
    items: list[ItemMarnExtraccion] = []
    for _, texto in candidatos:
        titulo = texto[:120] + ("..." if len(texto) > 120 else "")
        items.append(ItemMarnExtraccion(tipo="aviso", titulo=titulo, detalle=texto))
        if len(items) >= 5:
            break

    if not items:
        for bloque in soup.find_all(["div", "section"], limit=50):
            clases = " ".join(bloque.get("class", [])).lower()
            if not any(p in clases for p in ("alerta", "aviso", "noticia", "banner", "content")):
                continue
            titulo_el = bloque.find(["h2", "h3", "h4", "strong", "a"])
            texto_el = bloque.find("p")
            titulo = titulo_el.get_text(strip=True) if titulo_el else ""
            if not titulo or len(titulo) < 5:
                continue
            detalle = texto_el.get_text(strip=True)[:300] if texto_el else None
            items.append(ItemMarnExtraccion(tipo="aviso", titulo=titulo, detalle=detalle))
            if len(items) >= 5:
                break

    if not items:
        for enlace in soup.find_all("a", href=True):
            texto = enlace.get_text(strip=True)
            if not texto or len(texto) < 8:
                continue
            if not any(p in texto.lower() for p in ("boletín", "boletin", "informe", "comunicado", "clima", "meteorol", "pronost")):
                continue
            href = enlace["href"]
            if not href.startswith("http"):
                href = f"{base_url.rstrip('/')}/{href.lstrip('/')}"
            items.append(ItemMarnExtraccion(tipo="enlace", titulo=texto[:120], url=href))
            if len(items) >= 5:
                break

    if not items and soup.title:
        items.append(
            ItemMarnExtraccion(
                tipo="enlace",
                titulo=soup.title.get_text(strip=True)[:120],
                detalle="Consulte el sitio oficial para información actualizada.",
                url=base_url,
            )
        )

    return items


async def extraer_datos_portal_marn(cliente: httpx.AsyncClient) -> list[ItemMarnExtraccion]:
    base_url = str(ajustes.marn_portal_base_url).rstrip("/")
    html, _ = await _obtener_html(cliente, _URLS_MARN)
    if not html:
        return []
    return _extraer_items_desde_html(html, base_url)


async def extraer_datos_snet(cliente: httpx.AsyncClient) -> tuple[list[ItemMarnExtraccion], str | None]:
    html, url_final = await _obtener_html(
        cliente,
        (_URL_SNET_PRONOSTICO_48H, _URL_SNET_INFORMES, _URL_SNET_METEOROLOGIA),
    )
    if not html:
        return [], None
    items = _extraer_items_desde_html(html, "https://www.snet.gob.sv")
    return items, url_final


async def generar_resumen_marn_api_v1(latitud: float, longitud: float, altitud: float) -> ResumenMarnApiV1:
    base = _resumen_base(latitud, longitud, altitud)
    modo = ajustes.marn_intermedio_modo

    if modo == "off":
        return ResumenMarnApiV1(
            **base,
            modo=ModoResumenMarn.off,
            items=[],
            nota_metodologica="Integración con MARN desactivada por configuración.",
        )

    async with httpx.AsyncClient(
        timeout=ajustes.timeout_conexion,
        follow_redirects=True,
        headers=_HEADERS_NAVEGADOR,
    ) as cliente:
        try:
            estacion_srt = await obtener_estacion_srt_para_ubicacion(latitud, longitud, cliente)

            items_marn = await extraer_datos_portal_marn(cliente)
            if items_marn:
                resumen = ResumenMarnApiV1(
                    **base,
                    modo=ModoResumenMarn.portal,
                    fuente_oficial="Ministerio de Medio Ambiente y Recursos Naturales (MARN), El Salvador",
                    url_portal_consultado=str(ajustes.marn_portal_base_url),
                    items=items_marn,
                    nota_metodologica="Información extraída del portal público del MARN.",
                )
                return _aplicar_estacion_srt(resumen, estacion_srt)

            items_snet, url_snet = await extraer_datos_snet(cliente)
            if items_snet:
                resumen = ResumenMarnApiV1(
                    **base,
                    modo=ModoResumenMarn.snet,
                    fuente_oficial=(
                        "Dirección General del Observatorio de Amenazas (DGOA) — "
                        "SNET / Ministerio de Medio Ambiente (MARN)"
                    ),
                    url_portal_consultado=url_snet or _URL_SNET_PRONOSTICO_48H,
                    items=items_snet,
                    nota_metodologica=(
                        "El sitio www.marn.gob.sv no respondió en este momento. "
                        "Se muestra información del servicio meteorológico oficial SNET (DGOA-MARN)."
                    ),
                )
                return _aplicar_estacion_srt(resumen, estacion_srt)

            resumen = ResumenMarnApiV1(
                **base,
                modo=ModoResumenMarn.no_disponible,
                fuente_oficial="Ministerio de Medio Ambiente (MARN), El Salvador",
                url_portal_consultado=str(ajustes.marn_portal_base_url),
                items=_items_enlaces_oficiales(),
                nota_metodologica=(
                    "No fue posible leer el contenido en línea en este momento. "
                    "Use los enlaces oficiales para consultar pronósticos y alertas actualizadas."
                ),
            )
            return _aplicar_estacion_srt(resumen, estacion_srt)
        except Exception as exc:
            logger.exception("Error al generar resumen MARN: %s", exc)
            resumen = ResumenMarnApiV1(
                **base,
                modo=ModoResumenMarn.no_disponible,
                fuente_oficial="Ministerio de Medio Ambiente (MARN), El Salvador",
                url_portal_consultado=str(ajustes.marn_portal_base_url),
                items=_items_enlaces_oficiales(),
                nota_metodologica=(
                    "No fue posible obtener datos en línea en este momento. "
                    "Use los enlaces oficiales siguientes."
                ),
            )
            try:
                estacion_srt = await obtener_estacion_srt_para_ubicacion(latitud, longitud, cliente)
                return _aplicar_estacion_srt(resumen, estacion_srt)
            except Exception:
                return resumen
