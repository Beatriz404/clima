"""Estado en memoria de la última ejecución del batch (monitoreo /health)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

_ultima_ejecucion: dict[str, Any] | None = None


def registrar_ejecucion_batch(resumen: dict) -> None:
    global _ultima_ejecucion
    _ultima_ejecucion = {
        **resumen,
        "registrado_en": datetime.utcnow().isoformat(),
    }


def obtener_ultima_ejecucion_batch() -> dict[str, Any] | None:
    return _ultima_ejecucion
