"""Intereses del ahorro: calcular la tasa desde lo que paga el banco y sumarlos solos."""
from datetime import date

from gestor.calculos import tasa_desde_pago
from gestor.db import get_config_texto, get_db, set_config
from gestor.views.ahorro import aplicar_intereses


def test_tasa_desde_pago_diario():
    # $15 al día sobre $240.000 → ≈ 2,31% anual
    assert tasa_desde_pago(15, 240_000, "dia") == 2.31
    assert tasa_desde_pago(1_000, 240_000, "mes") == 5.12
    assert tasa_desde_pago(11_040, 240_000, "anio") == 4.6


def test_calcular_tasa_desde_la_pagina(client):
    client.post("/ahorro/", data={"tipo": "deposito", "fecha": "2026-10-01", "monto": "240000"})
    r = client.post("/ahorro/tasa/calcular", data={"pago": "15", "periodo": "dia"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "tu tasa anual es 2,31%" in html
    assert "≈ $15 al día" in html


def test_calcular_tasa_sin_saldo(client):
    r = client.post("/ahorro/tasa/calcular", data={"pago": "15", "periodo": "dia"}, follow_redirects=True)
    assert "Primero registra tu saldo" in r.get_data(as_text=True)


def _preparar(app, modo):
    with app.app_context():
        conn = get_db()
        conn.execute("INSERT INTO ahorro (fecha, tipo, descripcion, monto) VALUES ('2026-10-01', 'deposito', '', 240000)")
        set_config("tasa_ahorro", 2.31)
        set_config("interes_modo", modo)
        set_config("interes_desde", "2026-10-01")
        conn.commit()


def _filas_automaticas(app):
    with app.app_context():
        return [tuple(f) for f in get_db().execute(
            "SELECT fecha, descripcion, monto FROM ahorro WHERE descripcion LIKE '%automático%' ORDER BY fecha")]


def test_intereses_diarios(app):
    _preparar(app, "diario")
    with app.app_context():
        sumado = aplicar_intereses(get_db(), hoy=date(2026, 10, 11))   # 10 días terminados
        assert 148 <= sumado <= 152                                     # ≈ $15 diarios
        assert aplicar_intereses(get_db(), hoy=date(2026, 10, 11)) == 0  # no se repite
        aplicar_intereses(get_db(), hoy=date(2026, 11, 3))
    filas = _filas_automaticas(app)
    assert [f[1] for f in filas] == ["Intereses octubre 2026 (automático)", "Intereses noviembre 2026 (automático)"]
    assert filas[0][0] == "2026-10-31"
    assert 460 <= filas[0][2] <= 470    # 31 días de octubre
    assert 28 <= filas[1][2] <= 32      # 1 y 2 de noviembre


def test_intereses_mensuales(app):
    _preparar(app, "mensual")
    with app.app_context():
        assert aplicar_intereses(get_db(), hoy=date(2026, 10, 20)) == 0   # aún no termina el mes
        assert 280 <= float(get_config_texto("interes_pendiente")) <= 290
        aplicar_intereses(get_db(), hoy=date(2026, 11, 2))
    filas = _filas_automaticas(app)
    assert len(filas) == 1
    assert filas[0][0] == "2026-10-31"
    assert 460 <= filas[0][2] <= 470


def test_modo_manual_no_suma_nada(app):
    _preparar(app, "manual")
    with app.app_context():
        assert aplicar_intereses(get_db(), hoy=date(2026, 12, 1)) == 0
    assert _filas_automaticas(app) == []


def test_cambiar_modo_desde_la_pagina(client):
    client.post("/ahorro/tasa", data={"tasa": "4,6"})
    client.post("/ahorro/", data={"tipo": "deposito", "fecha": "2026-10-01", "monto": "1000000"})
    r = client.post("/ahorro/intereses/modo", data={"modo": "diario"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "se sumarán solos cada día" in html
    assert 'value="diario" selected' in html
