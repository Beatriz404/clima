# Clima Agricola El Salvador

Aplicacion climatica para agricultura usando datos gratuitos de Open-Meteo, ajuste con machine learning en scikit-learn y recomendaciones de siembra para cualquier punto de El Salvador.

## Caracteristicas

- **Pre-cálculo batch** cada 30 min: consulta Open-Meteo para **14 ubicaciones** y guarda en SQLite.
- **Un solo módulo Open-Meteo**: `open_meteo.py` → `open_meteo_proxy.py` (caché, semáforo, anti-429).
- Backend en FastAPI con endpoints:
  - `GET /api/pronostico?ubicacion=San Salvador&dias=7` (lee de base de datos)
  - `GET /api/ubicaciones`
  - `POST /forecast` (tiempo real, legacy)
  - `POST /adjusted`
  - `POST /planting`
- Entradas por coordenadas: latitud, longitud y altitud.
- Modelo de ajuste (regresion con scikit-learn) con estacionalidad por fecha.
- Reglas agronomicas para decidir dias aptos de siembra.
- Persistencia de historicos y predicciones en SQLite.
- Frontend interactivo con mapa (Leaflet), estilo azul y consulta en tiempo real.

## Estructura

- `app/main.py`: API principal y rutas.
- `app/services/open_meteo_proxy.py`: proxy Open-Meteo (caché en memoria, anti-429, datos reales).
- `app/services/open_meteo.py`: formateo de pronósticos e históricos (usa el proxy).
- `app/services/ajuste_ml.py`: inferencia del modelo de ajuste.
- `app/services/agricultura.py`: logica de recomendacion de siembra.
- `app/ml/entrenar_modelo.py`: entrenamiento del modelo.
- `frontend/`: interfaz web interactiva con mapa.
- `tests/`: pruebas unitarias.

## Requisitos

- Python 3.10+
- pip install -r requirements.txt

## Ejecutar backend + frontend

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abrir: <http://127.0.0.1:8000>

Al iniciar, el servidor ejecuta el batch una vez y luego cada **30 minutos** (configurable en `.env`).

Monitoreo: `GET /api/sistema/estado` y `GET /health`.

## Batch manual / Cron

```bash
python scripts/actualizar_pronosticos.py
```

Cron Linux (`crontab -e`):

```cron
*/15 * * * * cd /ruta/clima && python scripts/actualizar_pronosticos.py >> logs/batch.log 2>&1
```

Windows: Programador de tareas cada 15 min con el comando anterior.

## Ubicaciones pre-calculadas (14)

San Salvador, Santa Ana, San Miguel, La Libertad, Sonsonate, Usulután, Chalatenango, Ahuachapán, Zacatecoluca, San Francisco Gotera, Cojutepeque, San Vicente, La Unión, Metapán.

## Variables de entorno (.env)

```env
BATCH_HABILITADO=true
BATCH_INTERVALO_MINUTOS=30
PRONOSTICO_SOLO_BATCH=true
PRONOSTICO_MAX_EDAD_MINUTOS=45
BATCH_AL_INICIAR=true

# Proxy Open-Meteo (caché en memoria, sin Redis)
CACHE_FORECAST_TTL=1800
CACHE_ARCHIVE_TTL=604800
OPEN_METEO_MAX_CONCURRENT=2
```

## Despliegue en Render (https://clima-glw1.onrender.com/)

1. Conecte el repositorio y use el archivo `render.yaml` (o copie variables de `.env.production.example`).
2. **Disco persistente** montado en `/var/data` para que SQLite no se borre al reiniciar.
3. Con `ENTORNO=produccion` y `PRONOSTICO_SOLO_BATCH=true`:
   - Solo el **batch cada 15 min** consulta Open-Meteo (14 ciudades).
   - Los usuarios leen siempre de base de datos (sin 429 en pantalla).
   - Parcelas en el mapa usan la **ciudad más cercana** del batch (datos reales Open-Meteo).
4. Tras el primer despliegue, espere 2–3 minutos a que termine el batch inicial.

### Proxy anti-429 (memoria + batch)

- Datos **siempre reales** desde `api.open-meteo.com`
- Producción: usuarios **no** llaman Open-Meteo en cada clic
- Caché forecast: 60 min en producción; cuadrícula del mapa ~2 km (`COORDENADAS_REDONDEO_GRADOS=0.02`)
- Backoff ante 429 en batch: pausa 12 s entre reintentos

## Entrenar modelo

```bash
python -m app.ml.entrenar_modelo
```

Esto guarda el modelo en `app/ml/modelo_ajuste.pkl`.

## Ejemplo de uso API

```bash
curl -X POST "http://127.0.0.1:8000/adjusted" ^
  -H "Content-Type: application/json" ^
  -d "{\"latitud\":13.6929,\"longitud\":-89.2182,\"altitud\":650,\"dias\":5}"
```

## Criterios de siembra implementados

- Temperatura ajustada ideal: 18-30 C.
- Lluvia moderada: 1-25 mm.
- Penalizacion por riesgo de lluvia extrema (probabilidad > 0.85).
- Dia apto si puntaje >= 65.


