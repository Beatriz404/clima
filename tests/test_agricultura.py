from app.services.agricultura import evaluar_dia_siembra


def test_dia_apto_siembra():
    resultado = evaluar_dia_siembra(temperatura_ajustada=24, lluvia_mm=8, probabilidad_lluvia=0.45)
    assert resultado.apto_siembra is True
    assert resultado.puntaje >= 65


def test_dia_no_apto_por_extremo():
    resultado = evaluar_dia_siembra(temperatura_ajustada=34, lluvia_mm=30, probabilidad_lluvia=0.9)
    assert resultado.apto_siembra is False
    assert resultado.puntaje < 65
