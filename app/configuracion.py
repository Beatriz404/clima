from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AjustesAplicacion(BaseSettings):
    """
    Configuración principal de la aplicación Clima Agrícola El Salvador.
    Las variables pueden ser sobreescritas mediante archivo .env o variables de entorno.
    """
    
    # Configuración básica de la aplicación
    nombre_app: str = "Clima Agrícola El Salvador"
    entorno: str = "desarrollo"  # desarrollo, testing, produccion
    debug: bool = Field(default=False, description="Modo debug para desarrollo")
    
    # Base de datos
    base_datos_url: str = Field(
        default="sqlite:///./clima_agricola.db",
        description="URL de conexión a la base de datos"
    )
    
    # APIs externas
    api_open_meteo_base: HttpUrl = Field(
        default="https://api.open-meteo.com/v1",
        description="URL base de la API de Open-Meteo para pronósticos"
    )
    api_open_meteo_archivo_base: HttpUrl = Field(
        default="https://archive-api.open-meteo.com/v1",
        description="URL base de la API de Open-Meteo para datos históricos"
    )
    
    # Zona horaria de El Salvador
    zona_horaria: str = Field(
        default="America/El_Salvador",
        description="Zona horaria para procesamiento de fechas"
    )
    
    # Modelo de Machine Learning
    ruta_modelo_ml: str = Field(
        default=str(Path("app/ml/modelo_ajuste.pkl")),
        description="Ruta al archivo del modelo entrenado"
    )
    
    # Configuración del MARN (Ministerio de Medio Ambiente)
    # URL opcional para complemento externo (debe ser del dominio marn.gob.sv)
    marn_complemento_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL del complemento MARN para datos adicionales (opcional)"
    )
    
    # Token opcional para API del MARN
    marn_api_token: Optional[str] = Field(
        default=None,
        repr=False,  # No mostrar en representaciones
        description="Token de autenticación para API del MARN (si requiere)"
    )
    
    # Portal oficial del MARN (CORREGIDO - URL correcta)
    marn_portal_base_url: HttpUrl = Field(
        default="https://www.marn.gob.sv/",
        description="Portal oficial del Ministerio de Medio Ambiente de El Salvador"
    )
    
    # Ruta específica dentro del portal (si aplica)
    marn_portal_path: str = Field(
        default="",
        description="Ruta específica dentro del portal MARN para consultas"
    )
    
    # Modo de operación para el resumen MARN
    # auto: intenta leer el portal real
    # demo: datos ilustrativos sin conexión real (con advertencia)
    # off: no consulta el portal
    marn_intermedio_modo: str = Field(
        default="auto",
        description="Modo de operación: auto (real), demo (ilustrativo), off (desactivado)"
    )
    
    # Timeout para conexiones externas (segundos)
    timeout_conexion: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Timeout para conexiones HTTP externas"
    )
    
    # Configuración de seguridad CORS
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:3000"
        ],
        description="Orígenes permitidos para CORS (no usar '*' en producción)"
    )
    
    # Rate limiting para protección contra abusos
    rate_limit_requests: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Máximo número de requests permitidos por ventana de tiempo"
    )
    
    rate_limit_window: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Ventana de tiempo para rate limiting (segundos)"
    )
    
    # Headers de seguridad
    enable_hsts: bool = Field(
        default=True,
        description="Habilitar HTTP Strict Transport Security"
    )
    
    enable_csp: bool = Field(
        default=True,
        description="Habilitar Content Security Policy"
    )
    
    # Logging y monitoreo
    log_level: str = Field(
        default="INFO",
        description="Nivel de logging: DEBUG, INFO, WARNING, ERROR"
    )
    
    log_requests: bool = Field(
        default=True,
        description="Registrar todas las requests entrantes"
    )
    
    # Cache
    cache_ttl: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Tiempo de vida del cache en segundos"
    )
    
    # Validación de coordenadas para El Salvador
    min_latitud: float = Field(default=13.0, description="Latitud mínima de El Salvador")
    max_latitud: float = Field(default=14.5, description="Latitud máxima de El Salvador")
    min_longitud: float = Field(default=-90.3, description="Longitud mínima de El Salvador")
    max_longitud: float = Field(default=-87.5, description="Longitud máxima de El Salvador")
    min_altitud: float = Field(default=0, description="Altitud mínima en metros")
    max_altitud: float = Field(default=3500, description="Altitud máxima en metros")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignorar variables extra en .env
    )
    
    # Validadores
    @field_validator('cors_origins')
    @classmethod
    def validar_cors_origins(cls, v: List[str]) -> List[str]:
        """Validar que la configuración CORS sea segura"""
        if '*' in v and len(v) > 1:
            raise ValueError('No se puede mezclar "*" (todos los orígenes) con otros orígenes específicos')
        
        # En producción, no permitir '*' si no es desarrollo
        # Nota: Esta validación es informativa, la lógica de producción debe estar en el código
        if '*' in v:
            import warnings
            warnings.warn(
                "⚠️ Configuración CORS insegura: permitiendo todos los orígenes con '*'. "
                "Esto NO es recomendable para producción.",
                UserWarning
            )
        
        return v
    
    @field_validator('marn_complemento_url')
    @classmethod
    def validar_url_marn(cls, v: Optional[HttpUrl]) -> Optional[HttpUrl]:
        """Validar que las URLs del MARN sean del dominio correcto"""
        if v is not None:
            url_str = str(v)
            # Permitir localhost para desarrollo, pero no en producción
            if 'localhost' not in url_str and '127.0.0.1' not in url_str:
                if 'marn.gob.sv' not in url_str and 'ambiente.gob.sv' not in url_str:
                    raise ValueError(
                        f'URL no válida: {url_str}. '
                        'Solo se permiten URLs del dominio marn.gob.sv o ambiente.gob.sv'
                    )
        return v
    
    @field_validator('marn_intermedio_modo')
    @classmethod
    def validar_modo_marn(cls, v: str) -> str:
        """Validar que el modo MARN sea válido"""
        modos_validos = ['auto', 'demo', 'off']
        if v.lower() not in modos_validos:
            raise ValueError(f'Modo MARN inválido: {v}. Debe ser uno de: {modos_validos}')
        return v.lower()
    
    @field_validator('entorno')
    @classmethod
    def validar_entorno(cls, v: str) -> str:
        """Validar que el entorno sea válido"""
        entornos_validos = ['desarrollo', 'testing', 'produccion']
        if v.lower() not in entornos_validos:
            raise ValueError(f'Entorno inválido: {v}. Debe ser uno de: {entornos_validos}')
        return v.lower()
    
    @field_validator('log_level')
    @classmethod
    def validar_log_level(cls, v: str) -> str:
        """Validar nivel de logging"""
        niveles_validos = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        nivel_upper = v.upper()
        if nivel_upper not in niveles_validos:
            raise ValueError(f'Nivel de log inválido: {v}. Debe ser uno de: {niveles_validos}')
        return nivel_upper
    
    # Propiedades útiles
    @property
    def es_desarrollo(self) -> bool:
        """Indica si el entorno es desarrollo"""
        return self.entorno.lower() == 'desarrollo'
    
    @property
    def es_produccion(self) -> bool:
        """Indica si el entorno es producción"""
        return self.entorno.lower() == 'produccion'
    
    @property
    def url_portal_marn_completa(self) -> str:
        """URL completa del portal MARN incluyendo path específico"""
        base = str(self.marn_portal_base_url).rstrip('/')
        if self.marn_portal_path:
            return f"{base}/{self.marn_portal_path.lstrip('/')}"
        return base
    
    @property
    def marn_modo_activo(self) -> bool:
        """Indica si la integración con MARN está activa"""
        return self.marn_intermedio_modo.lower() in ['auto', 'demo']
    
    @property
    def marn_modo_real(self) -> bool:
        """Indica si la integración con MARN es real (no demo)"""
        return self.marn_intermedio_modo.lower() == 'auto'
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Retorna la lista de orígenes CORS para FastAPI"""
        if '*' in self.cors_origins and not self.es_produccion:
            # En desarrollo, permitir todo (con advertencia)
            return ["*"]
        return self.cors_origins
    
    def get_database_url_with_params(self) -> str:
        """Retorna URL de base de datos con parámetros adicionales según el tipo"""
        if self.base_datos_url.startswith("sqlite"):
            # SQLite necesita parámetros especiales
            if "?" in self.base_datos_url:
                return f"{self.base_datos_url}&check_same_thread=False"
            else:
                return f"{self.base_datos_url}?check_same_thread=False"
        return self.base_datos_url
    
    def validate_coordinates(self, latitud: float, longitud: float, altitud: float) -> bool:
        """Valida que las coordenadas estén dentro de los límites de El Salvador"""
        return (
            self.min_latitud <= latitud <= self.max_latitud and
            self.min_longitud <= longitud <= self.max_longitud and
            self.min_altitud <= altitud <= self.max_altitud
        )


# Instancia global de configuración (caché para evitar recargar)
@lru_cache
def obtener_ajustes() -> AjustesAplicacion:
    """
    Obtiene la configuración de la aplicación.
    El resultado se cachea automáticamente gracias a @lru_cache.
    """
    return AjustesAplicacion()


# Ejemplo de uso:
if __name__ == "__main__":
    # Probar la configuración
    ajustes = obtener_ajustes()
    
    print("=" * 50)
    print("Configuración de Clima Agrícola El Salvador")
    print("=" * 50)
    print(f"Nombre App: {ajustes.nombre_app}")
    print(f"Entorno: {ajustes.entorno}")
    print(f"Modo debug: {ajustes.debug}")
    print(f"Base de datos: {ajustes.base_datos_url}")
    print(f"Portal MARN: {ajustes.url_portal_marn_completa}")
    print(f"Modo MARN: {ajustes.marn_intermedio_modo}")
    print(f"MARN activo: {ajustes.marn_modo_activo}")
    print(f"MARN real: {ajustes.marn_modo_real}")
    print(f"CORS origins: {ajustes.cors_origins_list}")
    print(f"Rate limiting: {ajustes.rate_limit_requests} requests / {ajustes.rate_limit_window} seg")
    print(f"Log level: {ajustes.log_level}")
    print(f"Timeout conexiones: {ajustes.timeout_conexion} seg")
    print(f"Cache TTL: {ajustes.cache_ttl} seg")
    print("=" * 50)
    
    # Probar validación de coordenadas
    test_coords = [
        (13.7, -89.2, 650),   # San Salvador - válido
        (15.0, -90.0, 1000),  # Fuera de límites - inválido
    ]
    
    print("\nValidación de coordenadas:")
    for lat, lon, alt in test_coords:
        valido = ajustes.validate_coordinates(lat, lon, alt)
        print(f"  ({lat}, {lon}, {alt}): {'✅ Válido' if valido else '❌ Inválido'}")
