from functools import lru_cache
import json
import warnings
from pathlib import Path
from typing import List, Optional

from pydantic import Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AjustesAplicacion(BaseSettings):
    nombre_app: str = "Clima Agrícola El Salvador"
    entorno: str = "desarrollo"
    debug: bool = Field(default=False, description="Modo debug")
    base_datos_url: str = Field(default="sqlite:///./clima_agricola.db")
    api_open_meteo_base: HttpUrl = Field(default="https://api.open-meteo.com/v1")
    api_open_meteo_archivo_base: HttpUrl = Field(default="https://archive-api.open-meteo.com/v1")
    zona_horaria: str = "America/El_Salvador"
    ruta_modelo_ml: str = Field(default=str(Path("app/ml/modelo_ajuste.pkl")))
    marn_complemento_url: Optional[HttpUrl] = Field(default=None)
    marn_api_token: Optional[str] = Field(default=None, repr=False)
    marn_portal_base_url: HttpUrl = Field(default="https://www.marn.gob.sv/")
    marn_portal_path: str = ""
    marn_intermedio_modo: str = Field(default="auto")
    timeout_conexion: int = Field(default=30, ge=5, le=120)
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:3000",
        ]
    )
    rate_limit_requests: int = Field(default=100, ge=10, le=1000)
    rate_limit_window: int = Field(default=60, ge=10, le=3600)
    log_level: str = Field(default="INFO")
    cache_ttl: int = Field(default=900, ge=60, le=3600)
    cache_forecast_ttl: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="TTL caché pronóstico en memoria (segundos)",
    )
    cache_archive_ttl: int = Field(
        default=604800,
        ge=3600,
        le=2592000,
        description="TTL caché histórico en memoria (7 días)",
    )
    open_meteo_max_concurrent: int = Field(default=2, ge=1, le=20)
    httpx_max_connections: int = Field(default=10, ge=2, le=100)
    httpx_max_keepalive_connections: int = Field(default=5, ge=1, le=50)
    batch_habilitado: bool = Field(default=True, description="Scheduler de pre-cálculo cada N minutos")
    batch_intervalo_minutos: int = Field(default=30, ge=5, le=120)
    batch_al_iniciar: bool = Field(default=True, description="Ejecutar batch al arrancar la API")
    pronostico_max_edad_minutos: int = Field(
        default=45,
        ge=5,
        le=180,
        description="Si el cache supera esta edad, se refresca desde Open-Meteo al consultar",
    )
    pronostico_solo_batch: bool = Field(
        default=False,
        description="En true, las peticiones de usuario no llaman Open-Meteo (solo el batch)",
    )
    coordenadas_redondeo_grados: float = Field(
        default=0.02,
        ge=0,
        le=0.1,
        description="Cuadrícula del mapa en grados (~2.2 km con 0.02); 0 desactiva",
    )
    coordenadas_cache_decimales: int = Field(
        default=2,
        ge=2,
        le=4,
        description="Decimales para clave de caché Open-Meteo en memoria",
    )
    min_latitud: float = Field(default=13.0)
    max_latitud: float = Field(default=14.5)
    min_longitud: float = Field(default=-90.3)
    max_longitud: float = Field(default=-87.5)
    min_altitud: float = Field(default=0)
    max_altitud: float = Field(default=3500)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            texto = v.strip()
            if texto.startswith("["):
                return json.loads(texto)
            return [item.strip() for item in texto.split(",") if item.strip()]
        return v

    @field_validator("cors_origins")
    @classmethod
    def validar_cors_origins(cls, v: List[str]) -> List[str]:
        if "*" in v and len(v) > 1:
            raise ValueError('No se puede mezclar "*" con otros orígenes')
        if "*" in v:
            warnings.warn(
                "CORS permite todos los orígenes (*). No recomendado en producción.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("marn_complemento_url")
    @classmethod
    def validar_url_marn(cls, v: Optional[HttpUrl]) -> Optional[HttpUrl]:
        if v is None:
            return v
        url_str = str(v)
        if "localhost" in url_str or "127.0.0.1" in url_str:
            return v
        if "marn.gob.sv" not in url_str and "ambiente.gob.sv" not in url_str:
            raise ValueError("Solo se permiten URLs del dominio marn.gob.sv o ambiente.gob.sv")
        return v

    @field_validator("marn_intermedio_modo")
    @classmethod
    def validar_modo_marn(cls, v: str) -> str:
        valor = v.lower().strip()
        if valor == "demo":
            valor = "auto"
        modos = {"auto", "off"}
        if valor not in modos:
            raise ValueError(f"Modo MARN inválido: {v}. Debe ser: auto u off")
        return valor

    @field_validator("entorno")
    @classmethod
    def validar_entorno(cls, v: str) -> str:
        entornos = {"desarrollo", "testing", "produccion"}
        valor = v.lower()
        if valor not in entornos:
            raise ValueError(f"Entorno inválido: {v}")
        return valor

    @field_validator("log_level")
    @classmethod
    def validar_log_level(cls, v: str) -> str:
        niveles = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        nivel = v.upper()
        if nivel not in niveles:
            raise ValueError(f"Nivel de log inválido: {v}")
        return nivel

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"

    @property
    def url_portal_marn_completa(self) -> str:
        base = str(self.marn_portal_base_url).rstrip("/")
        if self.marn_portal_path:
            return f"{base}/{self.marn_portal_path.lstrip('/')}"
        return base

    def validate_coordinates(self, latitud: float, longitud: float, altitud: float) -> bool:
        return (
            self.min_latitud <= latitud <= self.max_latitud
            and self.min_longitud <= longitud <= self.max_longitud
            and self.min_altitud <= altitud <= self.max_altitud
        )

    @model_validator(mode="after")
    def aplicar_valores_produccion(self) -> "AjustesAplicacion":
        if self.entorno != "produccion":
            return self
        cambios: dict = {}
        if not self.pronostico_solo_batch:
            cambios["pronostico_solo_batch"] = True
        if self.batch_intervalo_minutos < 30:
            cambios["batch_intervalo_minutos"] = 30
        if self.pronostico_max_edad_minutos < 45:
            cambios["pronostico_max_edad_minutos"] = 45
        if self.cache_forecast_ttl < 1800:
            cambios["cache_forecast_ttl"] = 1800
        if self.open_meteo_max_concurrent > 1:
            cambios["open_meteo_max_concurrent"] = 1
        if cambios:
            return self.model_copy(update=cambios)
        return self


@lru_cache
def obtener_ajustes() -> AjustesAplicacion:
    return AjustesAplicacion()
