from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
from sklearn.neural_network import MLPRegressor

from app.configuracion import obtener_ajustes

ajustes = obtener_ajustes()


@dataclass
class SalidaAjuste:
    temperatura_ajustada: float
    probabilidad_lluvia_ajustada: float


class ModeloAjusteClima:
    def __init__(self, ruta_modelo: str | None = None):
        self.ruta_modelo = ruta_modelo or ajustes.ruta_modelo_ml
        self._modelo = self._cargar_modelo()

    def _cargar_modelo(self) -> MLPRegressor | None:
        ruta = Path(self.ruta_modelo)
        if ruta.exists():
            with ruta.open("rb") as archivo:
                return pickle.load(archivo)
        return None

    @staticmethod
    def _features_entrada(
        latitud: float,
        longitud: float,
        altitud: float,
        temperatura: float,
        lluvia_mm: float,
        humedad_relativa: float,
        fecha: date,
    ) -> np.ndarray:
        dia_anio = datetime(fecha.year, fecha.month, fecha.day).timetuple().tm_yday
        sin_estacion = np.sin(2 * np.pi * dia_anio / 365)
        cos_estacion = np.cos(2 * np.pi * dia_anio / 365)
        return np.array(
            [latitud, longitud, altitud / 1000.0, temperatura, lluvia_mm, humedad_relativa / 100.0, sin_estacion + cos_estacion],
            dtype=np.float32,
        ).reshape(1, -1)

    def ajustar(
        self,
        latitud: float,
        longitud: float,
        altitud: float,
        temperatura: float,
        lluvia_mm: float,
        humedad_relativa: float,
        fecha: date,
    ) -> SalidaAjuste:
        entrada = self._features_entrada(latitud, longitud, altitud, temperatura, lluvia_mm, humedad_relativa, fecha)
        if self._modelo is not None:
            pred = self._modelo.predict(entrada)[0]
            temperatura_ajustada = float(pred[0])
            prob_lluvia = float(np.clip(pred[1], 0, 1))
            return SalidaAjuste(temperatura_ajustada=temperatura_ajustada, probabilidad_lluvia_ajustada=prob_lluvia)

        # Fallback heurístico hasta tener entrenamiento real del modelo.
        ajuste_altitud = -0.0065 * altitud
        ajuste_humedad = (humedad_relativa - 70) * 0.02
        temperatura_ajustada = temperatura + ajuste_altitud + ajuste_humedad
        prob_lluvia = float(np.clip((lluvia_mm / 20.0) + (humedad_relativa / 100.0) * 0.4, 0, 1))
        return SalidaAjuste(temperatura_ajustada=temperatura_ajustada, probabilidad_lluvia_ajustada=prob_lluvia)


modelo_ajuste_global = ModeloAjusteClima()
