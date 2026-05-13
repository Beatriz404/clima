from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AjustesAplicacion(BaseSettings):
    nombre_app: str = "Clima Agrícola El Salvador"
    entorno: str = "desarrollo"
    base_datos_url: str = "sqlite:///./clima_agricola.db"
    api_open_meteo_base: str = "https://api.open-meteo.com/v1"
    api_open_meteo_archivo_base: str = "https://archive-api.open-meteo.com/v1"
    zona_horaria: str = "America/El_Salvador"
    ruta_modelo_ml: str = str(Path("app/ml/modelo_ajuste.pkl"))
    # Complemento MARN (opcional): URL de un servicio que devuelva JSON con datos de la red nacional.
    # No afecta a Open-Meteo ni a los endpoints existentes; solo se usa en POST /marn/complemento.
    marn_complemento_url: str | None = None
    marn_api_token: str | None = Field(default=None, repr=False)
    # API intermedia documentada (GET /api/v1/nacional/marn/resumen)
    marn_portal_base_url: str = "https://www.marn.gob.sv/"
    marn_portal_path: str = ""
    # auto: intenta leer el portal | demo: datos ilustrativos sin red | off: no consulta red.
    marn_intermedio_modo: str = "auto"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def obtener_ajustes() -> AjustesAplicacion:
    return AjustesAplicacion()
