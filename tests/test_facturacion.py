"""Día de facturación de los créditos: períodos, cuotas cobradas y calendario."""
from datetime import date

from gestor.calculos import (calendario_cuotas, estado_cuotas, facturado_en,
                             periodo_facturacion, rango_periodo)
from gestor.db import conectar


def test_periodo_con_cierre_el_20():
    # Facturación el 20: el período de octubre va del 21 de septiembre al 20 de octubre
    assert periodo_facturacion(date(2026, 9, 20), 20) == "2026-09"
    assert periodo_facturacion(date(2026, 9, 21), 20) == "2026-10"
    assert periodo_facturacion(date(2026, 10, 20), 20) == "2026-10"
    assert periodo_facturacion(date(2026, 10, 21), 20) == "2026-11"
    assert periodo_facturacion(date(2026, 12, 25), 20) == "2027-01"
    assert rango_periodo("2026-10", 20) == (date(2026, 9, 21), date(2026, 10, 20))
    assert rango_periodo("2027-01", 20) == (date(2026, 12, 21), date(2027, 1, 20))


def test_periodo_sin_dia_es_el_mes_calendario():
    assert periodo_facturacion(date(2026, 10, 31)) == "2026-10"
    assert rango_periodo("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))


def test_dia_31_en_meses_cortos():
    assert rango_periodo("2026-03", 31) == (date(2026, 3, 1), date(2026, 3, 31))
    assert rango_periodo("2026-02", 31) == (date(2026, 2, 1), date(2026, 2, 28))
    assert periodo_facturacion(date(2026, 2, 28), 31) == "2026-02"
    assert periodo_facturacion(date(2026, 3, 1), 31) == "2026-03"


def test_cuotas_cobradas_segun_el_cierre():
    # Compra el 5 de octubre: entra al estado que cierra el 20 de octubre
    assert estado_cuotas(90_000, 3, date(2026, 10, 5), date(2026, 10, 20), dia_facturacion=20).facturadas == 0
    assert estado_cuotas(90_000, 3, date(2026, 10, 5), date(2026, 10, 21), dia_facturacion=20).facturadas == 1
    # Compra el 25 de octubre: es del período de noviembre
    assert estado_cuotas(90_000, 3, date(2026, 10, 25), date(2026, 11, 1), dia_facturacion=20).facturadas == 0
    assert estado_cuotas(90_000, 3, date(2026, 10, 25), date(2026, 11, 21), dia_facturacion=20).facturadas == 1
    # Sin día de facturación se mantiene lo de antes (cambio de mes)
    assert estado_cuotas(90_000, 3, date(2026, 10, 25), date(2026, 11, 1)).facturadas == 1


def test_calendario_y_facturado():
    compras = [{"fecha": "2026-10-05", "monto": 30_000, "cuotas": 3},
               {"fecha": "2026-10-25", "monto": 10_000, "cuotas": 1}]
    cal = calendario_cuotas(compras, date(2026, 10, 30), 4, dia_facturacion=20)
    assert cal == {"2026-11": 10_000, "2026-12": 20_000, "2027-01": 10_000, "2027-02": 0}
    assert facturado_en(compras, "2026-10", 20) == 10_000
    assert facturado_en(compras, "2026-11", 20) == 20_000


def test_configurar_dia_en_la_cuenta(client, app):
    r = client.post("/credito/cuentas", data={"nombre": "Falabella", "cupo": "800000", "dia_facturacion": "20"})
    assert r.status_code == 302
    r = client.post("/credito/cuentas", data={"nombre": "BCI", "cupo": "1", "dia_facturacion": "40"},
                    follow_redirects=True)
    assert "entre 1 y 31" in r.get_data(as_text=True)
    with app.app_context():
        conn = conectar(app.config["DATABASE"])
        cuenta = conn.execute("SELECT * FROM credito_cuentas").fetchone()
        assert cuenta["dia_facturacion"] == 20
        assert conn.execute("SELECT COUNT(*) FROM credito_cuentas").fetchone()[0] == 1
        cid = cuenta["id"]

    client.post(f"/credito/cuentas/{cid}/compras",
                data={"fecha": "2026-09-25", "categoria": "Ropa", "monto": "30000", "cuotas": "1"})
    client.post(f"/credito/cuentas/{cid}/compras",
                data={"fecha": "2026-10-21", "categoria": "Ropa", "monto": "15000", "cuotas": "1"})
    html = client.get(f"/credito/?cuenta={cid}").get_data(as_text=True)
    assert "Facturación de octubre 2026" in html
    assert "21 sep al 20 oct" in html
    assert "Facturación de noviembre 2026" in html
    assert "cierra el día 20" in html

    # Se puede quitar el día (vuelve a fin de mes)
    client.post(f"/credito/cuentas/{cid}/editar", data={"nombre": "Falabella", "cupo": "800000", "dia_facturacion": ""})
    with app.app_context():
        conn = conectar(app.config["DATABASE"])
        assert conn.execute("SELECT dia_facturacion FROM credito_cuentas").fetchone()[0] is None
