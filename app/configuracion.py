from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AjustesAplicacion(BaseSettings):
    nombre_app: str = "Clima Agrícola El Salvador"
    entorno: str = "desarrollo"
    base_datos_url: str = "sqlite:///./clima_agricola.db"
    api_open_meteo_base: str = "https://api.open-meteo.com/v1"
    api_open_meteo_archivo_base: str = "https://archive-api.open-meteo.com/v1"
    zona_horaria: str = "America/El_Salvador"
    ruta_modelo_ml: str = str(Path("app/ml/modelo_ajuste.pkl"))
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def obtener_ajustes() -> AjustesAplicacion:
    return AjustesAplicacion()
