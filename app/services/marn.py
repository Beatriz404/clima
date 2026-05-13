"""
Complemento opcional con datos de la red nacional (MARN u otro backend que los exponga).

No sustituye ni modifica el flujo de Open-Meteo: solo se invoca desde el endpoint dedicado /marn/complemento.

Sugerencia: puede apuntar MARN_COMPLEMENTO_URL a la API pública documentada del mismo proyecto, por ejemplo
`https://<su-host>/api/v1/nacional/marn/resumen` (GET con latitud, longitud, altitud como query).
"""

from typing import Any

import httpx

from app.configuracion import obtener_ajustes


async def obtener_complemento_marn(latitud: float, longitud: float, altitud: float) -> dict[str, Any]:
    ajustes = obtener_ajustes()
    ubicacion = {"latitud": latitud, "longitud": longitud, "altitud": altitud}
    base = (ajustes.marn_complemento_url or "").strip()

    if not base:
        return {
            "ubicacion": ubicacion,
            "fuente": "MARN (red nacional)",
            "disponible": False,
            "mensaje": (
                "Integración lista. Defina MARN_COMPLEMENTO_URL en el entorno con la URL de su "
                "servicio intermedio o API que entregue datos MARN en JSON (mismo criterio de lat/lon/altitud)."
            ),
            "datos": None,
        }

    headers: dict[str, str] = {}
    token = (ajustes.marn_api_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as cliente:
            respuesta = await cliente.get(
                base,
                params={"latitud": latitud, "longitud": longitud, "altitud": altitud},
                headers=headers or None,
            )
            respuesta.raise_for_status()
            cuerpo = respuesta.json()
    except Exception as exc:  # noqa: BLE001 — queremos devolver mensaje claro al cliente
        return {
            "ubicacion": ubicacion,
            "fuente": "MARN (red nacional)",
            "disponible": False,
            "mensaje": f"No se pudo obtener el complemento MARN: {exc!s}",
            "datos": None,
        }

    if isinstance(cuerpo, dict):
        datos = cuerpo
    else:
        datos = {"valor": cuerpo}

    return {
        "ubicacion": ubicacion,
        "fuente": "MARN (red nacional)",
        "disponible": True,
        "mensaje": None,
        "datos": datos,
    }
