from __future__ import annotations

from datetime import datetime, timezone

from app.configuracion import obtener_ajustes
from app.esquemas import ModoResumenMarn


NOTA_METODOLOGICA = (
    "Resumen técnico independiente basado en información pública del portal MARN. "
    "Los datos mostrados son informativos y complementarios al pronóstico agrícola."
)


async def generar_resumen_marn_api_v1(
    latitud: float,
    longitud: float,
    altitud: float,
):
    """
    Genera un resumen simplificado compatible con el frontend.
    El frontend espera:
    
    {
        "alertas": [],
        "boletin": {}
    }
    """

    ajustes = obtener_ajustes()

    ahora = datetime.now(timezone.utc)

    modo_cfg = (ajustes.marn_intermedio_modo or "demo").strip().lower()

    # =========================================
    # MODO OFF
    # =========================================
    if modo_cfg == "off":
        return {
            "generado_en": ahora.isoformat(),
            "modo": ModoResumenMarn.off,
            "alertas": [],
            "boletin": {
                "fase": "Servicio deshabilitado",
                "pronostico": "No disponible",
                "temperatura": "--",
                "fecha": ahora.strftime("%d/%m/%Y"),
            },
            "nota_metodologica": (
                NOTA_METODOLOGICA
                + " El servicio fue deshabilitado por configuración."
            ),
        }


    alertas_demo = [
        {
            "fecha": ahora.strftime("%d/%m/%Y"),
            "mensaje": "Lluvias moderadas en zona central y occidental",
            "probabilidad": "70%",
        },
        {
            "fecha": ahora.strftime("%d/%m/%Y"),
            "mensaje": "Monitorear cultivos de maíz por humedad elevada",
            "probabilidad": "",
        },
    ]

    boletin_demo = {
        "fase": "Transición a invierno",
        "pronostico": "Inicio de canícula en aproximadamente 15 días",
        "temperatura": "24°C - 32°C",
        "fecha": ahora.strftime("%d/%m/%Y"),
    }

    return {
        "generado_en": ahora.isoformat(),
        "modo": ModoResumenMarn.demo,
        "consulta": {
            "latitud": latitud,
            "longitud": longitud,
            "altitud": altitud,
        },
        "alertas": alertas_demo,
        "boletin": boletin_demo,
        "nota_metodologica": NOTA_METODOLOGICA,
    }