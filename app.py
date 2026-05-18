import os
import warnings
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, render_template, request
from keras.layers import Dense, Dropout, LSTM
from keras.models import Sequential
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_STATIC = os.path.join(BASE_DIR, "static")
CARPETA_GRAFICOS = os.path.join(CARPETA_STATIC, "graficos")

os.makedirs(CARPETA_GRAFICOS, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "desarrollo-clima-lstm")


def generar_datos_sinteticos():
    np.random.seed(42)
    horas = np.arange(720)
    temperatura = (
        15
        + 8 * np.sin(2 * np.pi * horas / 24)
        + 3 * np.sin(2 * np.pi * horas / 720)
        + np.random.randn(720) * 2
    )
    humedad = 65 + 15 * np.cos(2 * np.pi * horas / 24) + np.random.randn(720) * 10
    precipitacion = np.random.exponential(0.5, 720)
    precipitacion[precipitacion < 0.05] = 0
    viento = 5 + 3 * np.sin(2 * np.pi * horas / 12) + np.random.randn(720) * 2
    datos = pd.DataFrame(
        {
            "temperatura": temperatura,
            "humedad": humedad,
            "precipitacion": precipitacion,
            "velocidad_viento": viento,
        }
    )
    return datos


def obtener_datos_climaticos_historicos():
    fecha_fin = datetime.now()
    fecha_inicio = fecha_fin - timedelta(days=30)
    parametros = {
        "latitude": 13.4833,
        "longitude": -88.1833,
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "wind_speed_10m",
        ],
        "start_date": fecha_inicio.strftime("%Y-%m-%d"),
        "end_date": fecha_fin.strftime("%Y-%m-%d"),
        "timezone": "Europe/Madrid",
    }
    url = "https://archive-api.open-meteo.com/v1/archive"
    try:
        respuesta = requests.get(url, params=parametros, timeout=30)
        respuesta.raise_for_status()
        datos_json = respuesta.json()
        datos = pd.DataFrame(
            {
                "temperatura": datos_json["hourly"]["temperature_2m"],
                "humedad": datos_json["hourly"]["relative_humidity_2m"],
                "precipitacion": datos_json["hourly"]["precipitation"],
                "velocidad_viento": datos_json["hourly"]["wind_speed_10m"],
            }
        )
        datos = datos.dropna()
        if len(datos) < 48:
            return generar_datos_sinteticos()
        return datos
    except Exception:
        return generar_datos_sinteticos()


def crear_secuencias(datos_matriz, longitud_secuencia=24):
    X_lista = []
    y_vector = []
    for i in range(len(datos_matriz) - longitud_secuencia):
        X_lista.append(datos_matriz[i : i + longitud_secuencia])
        y_vector.append(datos_matriz[i + longitud_secuencia][0])
    return np.array(X_lista), np.array(y_vector)


def ejecutar_pipeline_lstm(epocas=50):
    datos_climaticos = obtener_datos_climaticos_historicos()
    escalador = StandardScaler()
    datos_escalados = escalador.fit_transform(datos_climaticos)
    longitud_secuencia = 24
    X, y = crear_secuencias(datos_escalados, longitud_secuencia)
    if len(X) < 10:
        datos_climaticos = generar_datos_sinteticos()
        datos_escalados = escalador.fit_transform(datos_climaticos)
        X, y = crear_secuencias(datos_escalados, longitud_secuencia)
    division = int(0.8 * len(X))
    X_entrenamiento = X[:division]
    X_prueba = X[division:]
    y_entrenamiento = y[:division]
    y_prueba = y[division:]
    modelo = Sequential(
        [
            LSTM(
                64,
                activation="relu",
                return_sequences=True,
                input_shape=(longitud_secuencia, X.shape[2]),
            ),
            Dropout(0.2),
            LSTM(32, activation="relu"),
            Dropout(0.2),
            Dense(16, activation="relu"),
            Dense(1),
        ]
    )
    modelo.compile(optimizer="adam", loss="mse", metrics=["mae"])
    historial = modelo.fit(
        X_entrenamiento,
        y_entrenamiento,
        epochs=epocas,
        batch_size=32,
        validation_split=0.2,
        verbose=0,
    )
    perdida_prueba, mae_prueba = modelo.evaluate(X_prueba, y_prueba, verbose=0)
    y_predicho = modelo.predict(X_prueba, verbose=0)
    serie_temp = datos_climaticos["temperatura"].values
    media_temp = np.mean(serie_temp)
    std_temp = np.std(serie_temp)
    if std_temp < 1e-8:
        std_temp = 1.0
    ultimos_datos_escalados = datos_escalados[-longitud_secuencia:].reshape(
        1, longitud_secuencia, -1
    )
    prediccion_normalizada = modelo.predict(ultimos_datos_escalados, verbose=0)
    valor_predicho = float(prediccion_normalizada[0][0])
    temperatura_siguiente_hora = valor_predicho * std_temp + media_temp
    errores = y_prueba - y_predicho.flatten()
    fig_loss = plt.figure(figsize=(8, 5))
    plt.plot(historial.history["loss"], label="Entrenamiento")
    plt.plot(historial.history["val_loss"], label="Validación")
    plt.title("Pérdida del modelo")
    plt.xlabel("Épocas")
    plt.ylabel("MSE")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(CARPETA_GRAFICOS, "perdida.png"), dpi=120, bbox_inches="tight")
    plt.close()
    fig_pred = plt.figure(figsize=(8, 5))
    plt.plot(y_prueba[:100], label="Real", alpha=0.7)
    plt.plot(y_predicho[:100], label="Predicho", alpha=0.7)
    plt.title("Predicciones vs Valores Reales")
    plt.xlabel("Muestra")
    plt.ylabel("Temperatura (normalizada)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(CARPETA_GRAFICOS, "prediccion_vs_real.png"), dpi=120, bbox_inches="tight")
    plt.close()
    fig_serie = plt.figure(figsize=(8, 5))
    plt.plot(datos_climaticos["temperatura"].values, alpha=0.7)
    plt.title("Serie temporal de temperatura")
    plt.xlabel("Horas")
    plt.ylabel("Temperatura (Celsius)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(CARPETA_GRAFICOS, "serie_temporal.png"), dpi=120, bbox_inches="tight")
    plt.close()
    fig_hist = plt.figure(figsize=(8, 5))
    plt.hist(errores, bins=30, edgecolor="black", alpha=0.7)
    plt.title("Distribución de errores")
    plt.xlabel("Error de predicción")
    plt.ylabel("Frecuencia")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(CARPETA_GRAFICOS, "histograma_errores.png"), dpi=120, bbox_inches="tight")
    plt.close()
    ultimas_filas = datos_climaticos.tail(24)
    tabla_registros = []
    for indice, fila in ultimas_filas.iterrows():
        tabla_registros.append(
            {
                "temperatura": round(float(fila["temperatura"]), 2),
                "humedad": round(float(fila["humedad"]), 2),
                "precipitacion": round(float(fila["precipitacion"]), 4),
                "velocidad_viento": round(float(fila["velocidad_viento"]), 2),
            }
        )
    return {
        "temperatura_predicha": round(temperatura_siguiente_hora, 2),
        "mae_prueba": round(float(mae_prueba), 4),
        "perdida_prueba": round(float(perdida_prueba), 6),
        "tabla_datos": tabla_registros,
        "imagen_perdida": "graficos/perdida.png",
        "imagen_pred_vs_real": "graficos/prediccion_vs_real.png",
        "imagen_serie": "graficos/serie_temporal.png",
        "imagen_errores": "graficos/histograma_errores.png",
    }


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/predecir", methods=["GET", "POST"])
def predecir():
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        resultado = ejecutar_pipeline_lstm()
        if es_ajax:
            return jsonify({"ok": True, **resultado})
        return render_template("resultados.html", **resultado)
    except Exception as exc:
        mensaje = str(exc)
        if es_ajax:
            return jsonify({"ok": False, "error": mensaje}), 500
        return (
            render_template(
                "resultados.html",
                temperatura_predicha=None,
                error=mensaje,
                tabla_datos=[],
                mae_prueba=None,
                perdida_prueba=None,
                imagen_perdida=None,
                imagen_pred_vs_real=None,
                imagen_serie=None,
                imagen_errores=None,
            ),
            500,
        )


if __name__ == "__main__":
    app.run(debug=True)
