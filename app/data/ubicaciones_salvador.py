import unicodedata
from dataclasses import dataclass

from app.configuracion import obtener_ajustes


def _normalizar_nombre(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return sin_acentos.strip().lower()


@dataclass(frozen=True)
class UbicacionSalvador:
    nombre: str
    latitud: float
    longitud: float
    altitud: float
    region: str


UBICACIONES_SALVADOR: tuple[UbicacionSalvador, ...] = (
    UbicacionSalvador("San Salvador", 13.6929, -89.2182, 650.0, "Capital"),
    UbicacionSalvador("Santa Ana", 13.9944, -89.5597, 720.0, "Occidente"),
    UbicacionSalvador("San Miguel", 13.4833, -88.1833, 120.0, "Oriente"),
    UbicacionSalvador("La Libertad", 13.4883, -89.3220, 10.0, "Costa"),
    UbicacionSalvador("Sonsonate", 13.7190, -89.7242, 220.0, "Occidente"),
    UbicacionSalvador("Usulután", 13.3500, -88.4500, 150.0, "Zona arrocera"),
    UbicacionSalvador("Chalatenango", 14.0333, -88.9333, 450.0, "Norte"),
    UbicacionSalvador("Ahuachapán", 13.9167, -89.8500, 780.0, "Cafetalera"),
    UbicacionSalvador("Zacatecoluca", 13.5000, -88.8667, 180.0, "Centro"),
    UbicacionSalvador("San Francisco Gotera", 13.7000, -88.1000, 310.0, "Morazán"),
    UbicacionSalvador("Cojutepeque", 13.7167, -88.9333, 850.0, "Cuscatlán"),
    UbicacionSalvador("San Vicente", 13.6333, -88.7833, 390.0, "Centro"),
    UbicacionSalvador("La Unión", 13.3333, -87.8500, 5.0, "Oriente costero"),
    UbicacionSalvador("Metapán", 14.3333, -89.4500, 470.0, "Norte occidente"),
)

NOMBRES_UBICACIONES = {_normalizar_nombre(u.nombre): u for u in UBICACIONES_SALVADOR}


def buscar_por_nombre(nombre: str) -> UbicacionSalvador | None:
    return NOMBRES_UBICACIONES.get(_normalizar_nombre(nombre))


def redondear_coordenada(valor: float, paso: float) -> float:
    if paso <= 0:
        return valor
    return round(valor / paso) * paso


def aplicar_cuadricula_coordenadas(
    latitud: float,
    longitud: float,
    altitud: float,
    paso: float | None = None,
) -> tuple[float, float, float]:
    paso_grados = paso if paso is not None else obtener_ajustes().coordenadas_redondeo_grados
    if paso_grados <= 0:
        return latitud, longitud, altitud
    return (
        redondear_coordenada(latitud, paso_grados),
        redondear_coordenada(longitud, paso_grados),
        round(altitud, 0),
    )


def ubicacion_desde_coordenadas(
    latitud: float,
    longitud: float,
    altitud: float,
) -> UbicacionSalvador:
    """Punto del mapa en cuadrícula estable (reutiliza caché y BD)."""
    lat, lon, alt = aplicar_cuadricula_coordenadas(latitud, longitud, altitud)
    ref = ubicacion_mas_cercana(lat, lon)
    etiqueta = f"Parcela ({lat:.4f}, {lon:.4f})"
    return UbicacionSalvador(
        nombre=etiqueta,
        latitud=lat,
        longitud=lon,
        altitud=alt,
        region=f"Ref. {ref.region}",
    )


def ubicacion_mas_cercana(latitud: float, longitud: float) -> UbicacionSalvador:
    import math

    mejor = UBICACIONES_SALVADOR[0]
    mejor_dist = float("inf")
    for ubicacion in UBICACIONES_SALVADOR:
        dlat = math.radians(ubicacion.latitud - latitud)
        dlon = math.radians(ubicacion.longitud - longitud)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(latitud))
            * math.cos(math.radians(ubicacion.latitud))
            * math.sin(dlon / 2) ** 2
        )
        dist = 2 * math.asin(math.sqrt(a))
        if dist < mejor_dist:
            mejor_dist = dist
            mejor = ubicacion
    return mejor
