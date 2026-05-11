import asyncio
import pickle
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor

from app.configuracion import obtener_ajustes
from app.services.open_meteo import obtener_historico

ajustes = obtener_ajustes()


def _crear_features_objetivos(fila: dict, lat: float, lon: float, altitud: float):
    fecha = fila["fecha"]
    dia_anio = fecha.timetuple().tm_yday
    sin_estacion = np.sin(2 * np.pi * dia_anio / 365)
    cos_estacion = np.cos(2 * np.pi * dia_anio / 365)

    t_media = (fila["temperatura_max"] + fila["temperatura_min"]) / 2
    x = [lat, lon, altitud / 1000.0, t_media, fila["lluvia_mm"], fila["humedad_relativa"] / 100.0, sin_estacion + cos_estacion]

    # Proxy supervisado: usa consistencia física simple cuando no hay estación local.
    t_obj = t_media + (-0.0065 * altitud) + (fila["humedad_relativa"] - 70) * 0.02
    p_obj = np.clip((fila["lluvia_mm"] / 20.0) + (fila["humedad_relativa"] / 100.0) * 0.4, 0, 1)
    y = [t_obj, p_obj]
    return x, y


async def entrenar():
    ubicaciones_entrenamiento = [
        (13.6929, -89.2182, 650),  # San Salvador
        (13.9950, -89.5590, 20),  # Sonsonate
        (13.4800, -88.1800, 95),  # San Miguel
        (14.0370, -88.9320, 745),  # Santa Ana
    ]

    fecha_fin = date.today() - timedelta(days=1)
    fecha_inicio = fecha_fin - timedelta(days=360)

    x_total: list[list[float]] = []
    y_total: list[list[float]] = []

    for lat, lon, alt in ubicaciones_entrenamiento:
        historico = await obtener_historico(lat, lon, alt, fecha_inicio.isoformat(), fecha_fin.isoformat())
        for fila in historico:
            x, y = _crear_features_objetivos(fila, lat, lon, alt)
            x_total.append(x)
            y_total.append(y)

    x_np = np.array(x_total, dtype=np.float32)
    y_np = np.array(y_total, dtype=np.float32)

    x_entrenamiento, x_prueba, y_entrenamiento, y_prueba = train_test_split(
        x_np, y_np, test_size=0.2, random_state=42
    )

    modelo = MLPRegressor(
        hidden_layer_sizes=(24, 16),
        activation="relu",
        solver="adam",
        learning_rate_init=0.001,
        max_iter=600,
        random_state=42,
    )
    modelo.fit(x_entrenamiento, y_entrenamiento)
    puntaje = modelo.score(x_prueba, y_prueba)

    ruta = Path(ajustes.ruta_modelo_ml)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("wb") as archivo:
        pickle.dump(modelo, archivo)
    print(f"Modelo guardado en {ruta} con R2={puntaje:.4f}")


if __name__ == "__main__":
    asyncio.run(entrenar())
