import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from app.esquemas import EstacionSrtDiaria

logger = logging.getLogger(__name__)

URL_SRT_DIARIOS = "https://srt.ambiente.gob.sv/old/index.php?rutina=ver_diarios"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-SV,es;q=0.9",
}

_RUTA_COORDS = Path(__file__).resolve().parent.parent / "data" / "estaciones_srt_coords.json"


@dataclass
class FilaEstacionSrt:
    indice: str
    nombre: str
    lluvia_mm: float | None
    temp_max_dia_anterior_c: float | None
    temp_min_dia_actual_c: float | None
    humedad_relativa_pct: float | None


def _cargar_coordenadas() -> dict[str, dict]:
    if not _RUTA_COORDS.exists():
        return {}
    with _RUTA_COORDS.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def _a_float(valor: str) -> float | None:
    texto = (valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radio = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radio * 2 * math.asin(math.sqrt(min(1.0, a)))


def _extraer_fecha_reporte(soup: BeautifulSoup) -> str | None:
    for etiqueta in soup.find_all(["label", "strong", "h3", "h4", "p", "span"]):
        texto = etiqueta.get_text(" ", strip=True)
        if "fecha" not in texto.lower():
            continue
        match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", texto)
        if match:
            return match.group(1)
        hermano = etiqueta.find_next(["input", "span", "b", "strong"])
        if hermano:
            valor = hermano.get("value") or hermano.get_text(strip=True)
            if valor and re.search(r"\d", valor):
                return valor.strip()
    return datetime.now().strftime("%d/%m/%Y")


def _parsear_tabla(html: str) -> tuple[str | None, list[FilaEstacionSrt]]:
    soup = BeautifulSoup(html, "html.parser")
    fecha = _extraer_fecha_reporte(soup)
    filas: list[FilaEstacionSrt] = []

    for tabla in soup.find_all("table"):
        encabezados = [th.get_text(strip=True).lower() for th in tabla.find_all("th")]
        if not encabezados or "estaci" not in "".join(encabezados):
            continue
        for tr in tabla.find_all("tr")[1:]:
            celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(celdas) < 6:
                continue
            indice = celdas[0].strip()
            nombre = celdas[1].strip()
            if not indice or not nombre or indice.lower() == "indice":
                continue
            filas.append(
                FilaEstacionSrt(
                    indice=indice,
                    nombre=nombre,
                    lluvia_mm=_a_float(celdas[2]),
                    temp_max_dia_anterior_c=_a_float(celdas[3]),
                    temp_min_dia_actual_c=_a_float(celdas[4]),
                    humedad_relativa_pct=_a_float(celdas[5]),
                )
            )
        if filas:
            break

    return fecha, filas


async def obtener_reporte_srt_diario(
    cliente: httpx.AsyncClient | None = None,
) -> tuple[str | None, list[FilaEstacionSrt]]:
    cerrar = False
    if cliente is None:
        cliente = httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_HEADERS)
        cerrar = True
    try:
        respuesta = await cliente.get(URL_SRT_DIARIOS)
        respuesta.raise_for_status()
        return _parsear_tabla(respuesta.text)
    except Exception as exc:
        logger.warning("SRT diarios: no se pudo obtener reporte: %s", exc)
        return None, []
    finally:
        if cerrar:
            await cliente.aclose()


def estacion_mas_cercana(
    latitud: float,
    longitud: float,
    filas: list[FilaEstacionSrt],
    fecha_reporte: str | None,
) -> EstacionSrtDiaria | None:
    if not filas:
        return None

    coords = _cargar_coordenadas()
    mejor: EstacionSrtDiaria | None = None
    menor_distancia = float("inf")

    for fila in filas:
        geo = coords.get(fila.indice.upper())
        if not geo:
            continue
        dist = _distancia_km(latitud, longitud, geo["lat"], geo["lon"])
        if dist < menor_distancia:
            menor_distancia = dist
            mejor = EstacionSrtDiaria(
                indice=fila.indice,
                nombre=fila.nombre,
                fecha_reporte=fecha_reporte,
                lluvia_mm=fila.lluvia_mm,
                temp_max_dia_anterior_c=fila.temp_max_dia_anterior_c,
                temp_min_dia_actual_c=fila.temp_min_dia_actual_c,
                humedad_relativa_pct=fila.humedad_relativa_pct,
                distancia_km=round(dist, 1),
                latitud_estacion=geo["lat"],
                longitud_estacion=geo["lon"],
            )

    if mejor is not None:
        return mejor

    fila = filas[0]
    return EstacionSrtDiaria(
        indice=fila.indice,
        nombre=fila.nombre,
        fecha_reporte=fecha_reporte,
        lluvia_mm=fila.lluvia_mm,
        temp_max_dia_anterior_c=fila.temp_max_dia_anterior_c,
        temp_min_dia_actual_c=fila.temp_min_dia_actual_c,
        humedad_relativa_pct=fila.humedad_relativa_pct,
        distancia_km=None,
        latitud_estacion=None,
        longitud_estacion=None,
    )


async def obtener_estacion_srt_para_ubicacion(
    latitud: float,
    longitud: float,
    cliente: httpx.AsyncClient,
) -> EstacionSrtDiaria | None:
    fecha, filas = await obtener_reporte_srt_diario(cliente)
    return estacion_mas_cercana(latitud, longitud, filas, fecha)
