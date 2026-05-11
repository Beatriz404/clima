from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.configuracion import obtener_ajustes

ajustes = obtener_ajustes()

argumentos_engine = {"check_same_thread": False} if ajustes.base_datos_url.startswith("sqlite") else {}
engine = create_engine(ajustes.base_datos_url, connect_args=argumentos_engine)
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def obtener_sesion():
    sesion = SesionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
