from datetime import date, datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.data.ubicaciones_salvador import UbicacionSalvador
from app.modelos import PronosticoSiembra

FUENTE_OPEN_METEO = "Open-Meteo"


def guardar_pronosticos_ubicacion(
    sesion: Session,
    ubicacion: UbicacionSalvador,
    registros: list[dict],
) -> int:
    ahora = datetime.utcnow()
    guardados = 0
    for registro in registros:
        fecha: date = registro["fecha"]
        existente = (
            sesion.query(PronosticoSiembra)
            .filter_by(ubicacion_nombre=ubicacion.nombre, fecha_pronostico=fecha)
            .first()
        )
        if existente:
            existente.latitud = ubicacion.latitud
            existente.longitud = ubicacion.longitud
            existente.temp_max = registro["temp_max"]
            existente.temp_min = registro["temp_min"]
            existente.lluvia_mm = registro["lluvia_mm"]
            existente.humedad = registro["humedad"]
            existente.velocidad_viento = registro["velocidad_viento"]
            existente.fuente_datos = FUENTE_OPEN_METEO
            existente.updated_at = ahora
        else:
            sesion.add(
                PronosticoSiembra(
                    ubicacion_nombre=ubicacion.nombre,
                    latitud=ubicacion.latitud,
                    longitud=ubicacion.longitud,
                    fecha_pronostico=fecha,
                    temp_max=registro["temp_max"],
                    temp_min=registro["temp_min"],
                    lluvia_mm=registro["lluvia_mm"],
                    humedad=registro["humedad"],
                    velocidad_viento=registro["velocidad_viento"],
                    fuente_datos=FUENTE_OPEN_METEO,
                    created_at=ahora,
                    updated_at=ahora,
                )
            )
        guardados += 1
    sesion.commit()
    return guardados


def obtener_pronostico_db(
    sesion: Session,
    ubicacion: UbicacionSalvador,
    dias: int,
) -> tuple[list[PronosticoSiembra], datetime | None]:
    hoy = date.today()
    filas = (
        sesion.query(PronosticoSiembra)
        .filter(
            PronosticoSiembra.ubicacion_nombre == ubicacion.nombre,
            PronosticoSiembra.fecha_pronostico >= hoy,
        )
        .order_by(PronosticoSiembra.fecha_pronostico)
        .limit(dias)
        .all()
    )
    ultima = (
        sesion.query(PronosticoSiembra.updated_at)
        .filter_by(ubicacion_nombre=ubicacion.nombre)
        .order_by(desc(PronosticoSiembra.updated_at))
        .first()
    )
    ultima_actualizacion = ultima[0] if ultima else None
    return filas, ultima_actualizacion
