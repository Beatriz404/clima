import os

# Evita batch real a Open-Meteo durante las pruebas unitarias.
os.environ.setdefault("BATCH_HABILITADO", "false")
os.environ.setdefault("BATCH_AL_INICIAR", "false")
os.environ.setdefault("REDIS_URL", "memory://")

import pytest

from app.base_datos import Base, engine

@pytest.fixture(scope="session", autouse=True)
def crear_tablas():
    Base.metadata.create_all(bind=engine)
    yield
