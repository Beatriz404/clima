"""Rutas de administración y estado del batch."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.base_datos import obtener_sesion
from app.configuracion import obtener_ajustes
from app.data.ubicaciones_salvador import UBICACIONES_SALVADOR
from app.services.batch_estado import obtener_ultima_ejecucion_batch
from app.services.batch_pronostico import ejecutar_actualizacion_batch
from app.services.pronostico_repositorio import batch_tiene_datos, obtener_ultima_actualizacion_batch

router = APIRouter(prefix="/api", tags=["Administración batch"])


@router.get("/batch/estado")
async def estado_batch(sesion: Session = Depends(obtener_sesion)):
    """Indica si el batch ya pobló la base de datos."""
    ultima = obtener_ultima_actualizacion_batch(sesion)
    tiene_datos = batch_tiene_datos(sesion)
    cfg = obtener_ajustes()
    ultimo_resumen = obtener_ultima_ejecucion_batch()

    return {
        "batch_inicializado": tiene_datos,
        "ultima_actualizacion": ultima.isoformat() if ultima else None,
        "ultima_ejecucion_batch": ultimo_resumen,
        "ubicaciones_configuradas": len(UBICACIONES_SALVADOR),
        "batch_intervalo_minutos": cfg.batch_intervalo_minutos,
        "recomendacion": (
            None
            if tiene_datos
            else f"El batch se ejecuta cada {cfg.batch_intervalo_minutos} minutos. "
            "Puede forzar una actualización con POST /api/admin/ejecutar_batch"
        ),
        "url_manual_init": None if tiene_datos else "/api/admin/ejecutar_batch",
    }


@router.post("/admin/ejecutar_batch")
async def ejecutar_batch_manual():
    """Ejecuta el batch manualmente (recuperación o primera carga)."""
    resultado = await ejecutar_actualizacion_batch()
    return resultado
