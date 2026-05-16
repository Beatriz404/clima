from functools import lru_cache
from pathlib import Path
from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AjustesAplicacion(BaseSettings):
    nombre_app: str = "Clima Agrícola El Salvador"
    entorno: str = "desarrollo"
    base_datos_url: str = "sqlite:///./clima_agricola.db"
    api_open_meteo_base: str = "https://api.open-meteo.com/v1"
    api_open_meteo_archivo_base: str = "https://archive-api.open-meteo.com/v1"
    zona_horaria: str = "America/El_Salvador"
    ruta_modelo_ml: str = str(Path("app/ml/modelo_ajuste.pkl"))
    
    # ✅ Cambiado: ahora valida que sea URL válida
    marn_complemento_url: HttpUrl | None = Field(default=None, description="URL del complemento MARN")
    marn_api_token: str | None = Field(default=None, repr=False)
    
    # ✅ URLs correctas del MARN
    marn_portal_base_url: HttpUrl = Field(
        default="https://www.marn.gob.sv/",
        description="Portal oficial del MARN"
    )
    marn_portal_path: str = ""
    
    # auto: intenta leer el portal | demo: datos ilustrativos sin red | off: no consulta red.
    marn_intermedio_modo: str = "auto"
    
    # ✅ Nuevo: Configuración CORS segura
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"],
        description="Orígenes permitidos para CORS"
    )
    
    # ✅ Nuevo: Rate limiting
    rate_limit_requests: int = Field(default=100, description="Máximo de requests por minuto")
    rate_limit_window: int = Field(default=60, description="Ventana de tiempo en segundos")
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    # ✅ Validar que las URLs sean del dominio correcto
    @field_validator('marn_complemento_url')
    @classmethod
    def validar_url_marn(cls, v):
        if v and 'marn.gob.sv' not in str(v) and 'localhost' not in str(v):
            raise ValueError('Solo se permiten URLs del dominio marn.gob.sv o localhost')
        return v
    
    @field_validator('cors_origins')
    @classmethod
    def validar_cors_origins(cls, v):
        if '*' in v and len(v) > 1:
            raise ValueError('No se puede mezclar "*" con otros orígenes')
        return v


@lru_cache
def obtener_ajustes() -> AjustesAplicacion:
    return AjustesAplicacion()
