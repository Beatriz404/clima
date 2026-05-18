# Clima Agricola El Salvador

Aplicacion climatica para agricultura usando datos gratuitos de Open-Meteo, ajuste con machine learning en scikit-learn y recomendaciones de siembra para cualquier punto de El Salvador.

## Caracteristicas

- Backend en FastAPI con endpoints:
  - `POST /forecast`
  - `POST /adjusted`
  - `POST /planting`
- Entradas por coordenadas: latitud, longitud y altitud.
- Modelo de ajuste (regresion con scikit-learn) con estacionalidad por fecha.
- Reglas agronomicas para decidir dias aptos de siembra.
- Persistencia de historicos y predicciones en SQLite.
- Frontend interactivo con mapa (Leaflet), estilo azul y consulta en tiempo real.

## Estructura

- `app/main.py`: API principal y rutas.
- `app/services/open_meteo.py`: consumo de Open-Meteo (forecast + historicos).
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
uvicorn app.main:app --reload
```

Abrir: <http://127.0.0.1:8000>

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


