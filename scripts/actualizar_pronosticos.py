#!/usr/bin/env python3
"""Cron job: actualiza pronósticos de las 14 ubicaciones en la base de datos.

Uso (cada 15 minutos en Linux/macOS crontab):
    */15 * * * * cd /ruta/clima && python scripts/actualizar_pronosticos.py >> logs/batch.log 2>&1

Windows Task Scheduler:
    python C:\\Users\\clase\\Desktop\\clima\\scripts\\actualizar_pronosticos.py
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.base_datos import Base, engine
from app.services.batch_pronostico import ejecutar_actualizacion_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    resumen = asyncio.run(ejecutar_actualizacion_batch())
    print(resumen)


if __name__ == "__main__":
    main()
