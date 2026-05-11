from __future__ import annotations

from collections import defaultdict


def region_microclima(latitud: float, longitud: float, altitud: float) -> str:
    if altitud >= 900:
        return "Montana fresca"
    if latitud >= 13.95:
        return "Occidente templado"
    if longitud <= -89.5:
        return "Centro volcanico"
    if longitud >= -88.4:
        return "Oriente seco"
    return "Franja intermedia humeda"


def _nivel_por_puntaje(puntaje: float) -> str:
    if puntaje >= 70:
        return "alto"
    if puntaje >= 40:
        return "medio"
    return "bajo"


def riesgo_sequia(pronostico: list[dict], region: str) -> dict:
    lluvia_total = sum(d["lluvia_mm"] for d in pronostico)
    temp_media = sum((d["temperatura_max"] + d["temperatura_min"]) / 2 for d in pronostico) / max(len(pronostico), 1)

    base = max(0.0, 100 - lluvia_total * 4)
    if "seco" in region.lower():
        base += 12
    if temp_media >= 30:
        base += 10
    puntaje = float(min(100, max(0, base)))
    return {
        "nivel": _nivel_por_puntaje(puntaje),
        "puntaje": round(puntaje, 1),
        "descripcion": "Riesgo por baja lluvia acumulada y alta temperatura esperada.",
    }


def riesgo_exceso_lluvia(pronostico: list[dict], region: str) -> dict:
    max_lluvia = max((d["lluvia_mm"] for d in pronostico), default=0)
    lluvia_total = sum(d["lluvia_mm"] for d in pronostico)
    base = min(100.0, max_lluvia * 3 + (lluvia_total / 2))
    if "humeda" in region.lower():
        base += 8
    puntaje = float(min(100, max(0, base)))
    return {
        "nivel": _nivel_por_puntaje(puntaje),
        "puntaje": round(puntaje, 1),
        "descripcion": "Riesgo por eventos intensos de precipitacion y acumulado semanal.",
    }


def lluvia_por_mes(historico: list[dict]) -> list[dict]:
    acumulado: dict[str, float] = defaultdict(float)
    for fila in historico:
        clave = fila["fecha"].strftime("%Y-%m")
        acumulado[clave] += fila["lluvia_mm"]
    salida = [{"mes": mes, "lluvia_mm": round(mm, 2)} for mes, mm in sorted(acumulado.items())]
    return salida


def notificaciones_agricolas(
    pronostico: list[dict],
    riesgo_sequia_data: dict,
    riesgo_exceso_data: dict,
    recomendaciones: list[dict],
) -> list[str]:
    avisos: list[str] = []
    if pronostico and pronostico[0]["lluvia_mm"] >= 20:
        avisos.append("Lluvia fuerte en 24h")
    if riesgo_sequia_data["nivel"] in {"alto", "medio"}:
        avisos.append("Riesgo de sequia")
    if recomendaciones and len(recomendaciones) > 1 and recomendaciones[1]["apto_siembra"]:
        avisos.append("Ventana optima para sembrar manana")
    if riesgo_exceso_data["nivel"] == "alto":
        avisos.append("Posible exceso de lluvia: considerar drenaje preventivo")
    return avisos
