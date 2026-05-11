from dataclasses import dataclass


@dataclass
class EvaluacionSiembra:
    apto_siembra: bool
    puntaje: float
    razon: str


def evaluar_dia_siembra(temperatura_ajustada: float, lluvia_mm: float, probabilidad_lluvia: float) -> EvaluacionSiembra:
    puntaje = 100.0
    razones = []

    if not (18 <= temperatura_ajustada <= 30):
        puntaje -= 35
        razones.append("Temperatura fuera del rango ideal (18-30C)")
    else:
        razones.append("Temperatura adecuada")

    if lluvia_mm < 1:
        puntaje -= 20
        razones.append("Lluvia insuficiente")
    elif lluvia_mm > 25:
        puntaje -= 30
        razones.append("Lluvia excesiva")
    else:
        razones.append("Lluvia moderada")

    if probabilidad_lluvia > 0.85:
        puntaje -= 25
        razones.append("Riesgo alto de evento extremo")
    else:
        razones.append("Sin riesgo extremo detectado")

    puntaje = max(0.0, puntaje)
    apto = puntaje >= 65
    return EvaluacionSiembra(apto_siembra=apto, puntaje=puntaje, razon="; ".join(razones))
