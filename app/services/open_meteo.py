from datetime import datetime

import httpx

from app.configuracion import obtener_ajustes

ajustes = obtener_ajustes()


def _a_formato_diario(respuesta: dict, dias: int) -> list[dict]:
    diarios = respuesta["daily"]
    salida = []
    for i in range(min(dias, len(diarios["time"]))):
        salida.append(
            {
                "fecha": datetime.fromisoformat(diarios["time"][i]).date(),
                "temperatura_max": float(diarios["temperature_2m_max"][i]),
                "temperatura_min": float(diarios["temperature_2m_min"][i]),
                "lluvia_mm": float(diarios["precipitation_sum"][i]),
                "humedad_relativa": float(diarios["relative_humidity_2m_mean"][i]),
            }
        )
    return salida


async def obtener_pronostico(latitud: float, longitud: float, altitud: float, dias: int) -> list[dict]:
    url = f"{ajustes.api_open_meteo_base}/forecast"
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "elevation": altitud,
        "timezone": ajustes.zona_horaria,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean",
        "forecast_days": dias,
    }
    async with httpx.AsyncClient(timeout=25) as cliente:
        respuesta = await cliente.get(url, params=parametros)
        respuesta.raise_for_status()
        datos = respuesta.json()
    return _a_formato_diario(datos, dias)


async def obtener_historico(latitud: float, longitud: float, altitud: float, fecha_inicio: str, fecha_fin: str) -> list[dict]:
    url = f"{ajustes.api_open_meteo_archivo_base}/archive"
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "elevation": altitud,
        "timezone": ajustes.zona_horaria,
        "start_date": fecha_inicio,
        "end_date": fecha_fin,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean",
    }
    async with httpx.AsyncClient(timeout=25) as cliente:
        respuesta = await cliente.get(url, params=parametros)
        respuesta.raise_for_status()
        datos = respuesta.json()
    return _a_formato_diario(datos, dias=10000)
