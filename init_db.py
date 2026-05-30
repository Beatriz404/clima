#!/usr/bin/env python
"""Inicializa la base de datos ejecutando el batch una sola vez."""

import asyncio
import sys

from app.base_datos import Base, engine
from app.services.batch_pronostico import ejecutar_actualizacion_batch
from app.services.open_meteo_proxy import cerrar_proxy, iniciar_proxy


async def main() -> None:
    print("Inicializando base de datos con pronósticos Open-Meteo...")
    Base.metadata.create_all(bind=engine)
    await iniciar_proxy()

    try:
        resultado = await ejecutar_actualizacion_batch()
        print("\nResultado:")
        print(f"   Exitosas: {resultado['exitosas']}/{resultado['total']}")
        print(f"   Fallidas: {resultado['fallidas']}")

        if resultado["fallidas"] > 0:
            print("\nAlgunas ubicaciones no se actualizaron. Revise logs o reintente.")
            sys.exit(1)

        print("\nBase de datos inicializada correctamente.")
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)
    finally:
        await cerrar_proxy()


if __name__ == "__main__":
    asyncio.run(main())
