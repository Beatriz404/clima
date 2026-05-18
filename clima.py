import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
import requests
import warnings
warnings.filterwarnings('ignore')

print("Obteniendo datos climáticos en tiempo real...")

def obtener_datos_climaticos_historicos():
    """Obtiene datos climáticos históricos de los últimos 30 días"""
    
    fecha_fin = datetime.now()
    fecha_inicio = fecha_fin - timedelta(days=30)
    
    parametros = {
        "latitude": 13.4833,
        "longitude": -88.1833,
        "hourly": ["temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m"],
        "start_date": fecha_inicio.strftime("%Y-%m-%d"),
        "end_date": fecha_fin.strftime("%Y-%m-%d"),
        "timezone": "Europe/Madrid"
    }
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    
    try:
        print("Conectando a la API de Open-Meteo...")
        respuesta = requests.get(url, params=parametros, timeout=30)
        respuesta.raise_for_status()
        datos = respuesta.json()
        
        df = pd.DataFrame({
            'temperatura': datos['hourly']['temperature_2m'],
            'humedad': datos['hourly']['relative_humidity_2m'],
            'precipitacion': datos['hourly']['precipitation'],
            'velocidad_viento': datos['hourly']['wind_speed_10m']
        })
        
        print(f"Datos obtenidos: {len(df)} registros horarios")
        return df
        
    except Exception as e:
        print(f"Error obteniendo datos: {e}")
        print("Generando datos sintéticos como alternativa...")
        return generar_datos_sinteticos()

def generar_datos_sinteticos():
    np.random.seed(42)
    
    horas = np.arange(720)
    
    temperatura = 15 + 8 * np.sin(2 * np.pi * horas / 24) + \
                  3 * np.sin(2 * np.pi * horas / 720) + \
                  np.random.randn(720) * 2
    
    humedad = 65 + 15 * np.cos(2 * np.pi * horas / 24) + \
              np.random.randn(720) * 10
    
    precipitacion = np.random.exponential(0.5, 720)
    precipitacion[precipitacion < 0.05] = 0
    
    viento = 5 + 3 * np.sin(2 * np.pi * horas / 12) + np.random.randn(720) * 2
    
    df = pd.DataFrame({
        'temperatura': temperatura,
        'humedad': humedad,
        'precipitacion': precipitacion,
        'velocidad_viento': viento
    })
    
    print("Datos sintéticos generados correctamente")
    return df

print("Preparando datos para la red neuronal...")

datos_climaticos = obtener_datos_climaticos_historicos()

escalador = StandardScaler()
datos_escalados = escalador.fit_transform(datos_climaticos)

def crear_secuencias(datos, longitud_secuencia=24):
    X, y = [], []
    for i in range(len(datos) - longitud_secuencia):
        X.append(datos[i:i+longitud_secuencia])
        y.append(datos[i+longitud_secuencia][0])
    return np.array(X), np.array(y)

LONGITUD_SECUENCIA = 24
X, y = crear_secuencias(datos_escalados, LONGITUD_SECUENCIA)

print(f"Secuencias creadas: {X.shape[0]} muestras")

division = int(0.8 * len(X))
X_entrenamiento, X_prueba = X[:division], X[division:]
y_entrenamiento, y_prueba = y[:division], y[division:]

print(f"Entrenamiento: {X_entrenamiento.shape[0]} muestras")
print(f"Prueba: {X_prueba.shape[0]} muestras")

print("Creando red neuronal LSTM...")

modelo = Sequential([
    LSTM(64, activation='relu', return_sequences=True, input_shape=(LONGITUD_SECUENCIA, X.shape[2])),
    Dropout(0.2),
    LSTM(32, activation='relu'),
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dense(1)
])

modelo.compile(optimizer='adam', loss='mse', metrics=['mae'])

print(modelo.summary())

print("Entrenando el modelo...")

historial = modelo.fit(
    X_entrenamiento, y_entrenamiento,
    epochs=50,
    batch_size=32,
    validation_split=0.2,
    verbose=1
)

print("Evaluando modelo...")
perdida_prueba, mae_prueba = modelo.evaluate(X_prueba, y_prueba)
print(f"Error absoluto medio en prueba: {mae_prueba:.4f}")

print("Generando gráficos...")

plt.figure(figsize=(15, 10))

plt.subplot(2, 2, 1)
plt.plot(historial.history['loss'], label='Entrenamiento')
plt.plot(historial.history['val_loss'], label='Validación')
plt.title('Pérdida del modelo')
plt.xlabel('Épocas')
plt.ylabel('MSE')
plt.legend()
plt.grid(True)

plt.subplot(2, 2, 2)
y_predicho = modelo.predict(X_prueba)
plt.plot(y_prueba[:100], label='Real', alpha=0.7)
plt.plot(y_predicho[:100], label='Predicho', alpha=0.7)
plt.title('Predicciones vs Valores Reales')
plt.xlabel('Muestra')
plt.ylabel('Temperatura (normalizada)')
plt.legend()
plt.grid(True)

plt.subplot(2, 2, 3)
plt.plot(datos_climaticos['temperatura'].values, alpha=0.7)
plt.title('Serie temporal de temperatura')
plt.xlabel('Horas')
plt.ylabel('Temperatura (Celsius)')
plt.grid(True)

plt.subplot(2, 2, 4)
errores = y_prueba - y_predicho.flatten()
plt.hist(errores, bins=30, edgecolor='black', alpha=0.7)
plt.title('Distribución de errores')
plt.xlabel('Error de predicción')
plt.ylabel('Frecuencia')
plt.grid(True)

plt.tight_layout()
plt.show()

ultimos_datos = datos_escalados[-LONGITUD_SECUENCIA:].reshape(1, LONGITUD_SECUENCIA, -1)
prediccion_normalizada = modelo.predict(ultimos_datos)

prediccion_real = prediccion_normalizada[0][0] * np.std(datos_climaticos['temperatura'].values) + np.mean(datos_climaticos['temperatura'].values)

print(f"\nPREDICCIÓN:")
print(f"Basado en las últimas {LONGITUD_SECUENCIA} horas de datos")
print(f"Temperatura esperada para la próxima hora: {prediccion_real:.1f} Celsius")

print("\nDATOS DE LAS ÚLTIMAS 12 HORAS:")
for i in range(-12, 0):
    print(f"  Hora {i}: {datos_climaticos['temperatura'].iloc[i]:.1f} C")