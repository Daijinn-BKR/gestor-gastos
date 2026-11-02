from gestor.db import conectar


def contar(app, tabla):
    conn = conectar(app.config["DATABASE"])
    total = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    conn.close()
    return total


def test_paginas_cargan(client):
    for url in ["/", "/movimientos/", "/credito/", "/ahorro/"]:
        assert client.get(url).status_code == 200


def test_agregar_y_eliminar_movimiento(app, client):
    r = client.post("/movimientos/", data={
        "tipo": "egreso", "fecha": "2026-10-10", "categoria": "Alimentación",
        "descripcion": "Supermercado", "monto": "15.000",
    }, follow_redirects=True)
    assert "$15.000" in r.get_data(as_text=True)
    assert contar(app, "movimientos") == 1

    client.post("/movimientos/1/eliminar")
    assert contar(app, "movimientos") == 0


def test_monto_invalido_no_se_guarda(app, client):
    r = client.post("/movimientos/", data={
        "tipo": "ingreso", "fecha": "2026-10-10", "categoria": "Sueldo", "monto": "abc",
    }, follow_redirects=True)
    assert "número entero" in r.get_data(as_text=True)
    assert contar(app, "movimientos") == 0


def crear_cuenta(client, nombre="Falabella", cupo="500000"):
    client.post("/credito/cuentas", data={"nombre": nombre, "cupo": cupo})


def test_credito_sin_cuentas_pide_crear_una(client):
    assert "Agrega tu primer crédito" in client.get("/credito/").get_data(as_text=True)


def test_varias_cuentas_de_credito(app, client):
    crear_cuenta(client, "Falabella", "800.000")
    crear_cuenta(client, "BCI", "1.200.000")
    client.post("/credito/cuentas/2/compras", data={
        "fecha": "2026-10-01", "categoria": "Ropa", "monto": "60000", "cuotas": "3",
    })
    pagina_bci = client.get("/credito/?cuenta=2").get_data(as_text=True)
    pagina_falabella = client.get("/credito/?cuenta=1").get_data(as_text=True)
    assert "$60.000" in pagina_bci
    assert "No hay compras registradas en Falabella" in pagina_falabella

    # Nombre repetido no se permite
    r = client.post("/credito/cuentas", data={"nombre": "bci", "cupo": "1000"}, follow_redirects=True)
    assert "Ya tienes un crédito llamado" in r.get_data(as_text=True)
    assert contar(app, "credito_cuentas") == 2


def test_renombrar_y_eliminar_cuenta(app, client):
    crear_cuenta(client)
    client.post("/credito/cuentas/1/editar", data={"nombre": "CMR Falabella", "cupo": "900000"})
    assert "CMR Falabella" in client.get("/credito/").get_data(as_text=True)

    client.post("/credito/cuentas/1/compras", data={"fecha": "2026-10-01", "categoria": "Ropa", "monto": "1000"})
    client.post("/credito/cuentas/1/pagos", data={"fecha": "2026-10-02", "monto": "1000", "registrar_egreso": "on"})
    client.post("/credito/cuentas/1/eliminar")
    assert contar(app, "credito_cuentas") == 0
    assert contar(app, "credito_compras") == 0  # en cascada
    assert contar(app, "credito_pagos") == 0
    assert contar(app, "movimientos") == 1      # el egreso del pago se mantiene


def test_compra_con_interes(client):
    crear_cuenta(client)
    client.post("/credito/cuentas/1/compras", data={
        "fecha": "2026-10-01", "categoria": "Vivienda", "monto": "100000", "cuotas": "12", "interes": "2,1",
    })
    html = client.get("/credito/?cuenta=1").get_data(as_text=True)
    assert "2,1%" in html
    assert "en intereses" in html


def test_panel_de_creditos(client):
    crear_cuenta(client, "Falabella", "800.000")
    crear_cuenta(client, "BCI", "1.200.000")
    client.post("/credito/cuentas/1/compras", data={"fecha": "2026-10-01", "categoria": "Ropa",
                                                    "monto": "60000", "cuotas": "3"})
    client.post("/credito/cuentas/2/compras", data={"fecha": "2026-10-02", "categoria": "Vivienda",
                                                    "monto": "100000", "cuotas": "12", "interes": "2"})
    html = client.get("/credito/").get_data(as_text=True)   # sin ?cuenta → panel
    assert "📊 Panel" in html and 'class="pestanas__panel activo"' in html
    assert "Cuotas de los próximos 12 meses" in html
    assert "Falabella" in html and "BCI" in html
    assert "$13.472" in html          # intereses: 9.456 × 12 − 100.000 (al 2%) … redondeado por cuota
    assert "Ropa" in html and "Vivienda" in html


def test_panel_muestra_dolares(client):
    client.post("/credito/cuentas", data={"nombre": "BCI", "cupo": "1.000.000", "cupo_usd": "100"})
    client.post("/credito/cuentas", data={"nombre": "Falabella", "cupo": "500.000", "cupo_usd": "50"})
    client.post("/credito/cuentas/1/compras", data={"fecha": "2026-10-01", "categoria": "Entretención",
                                                    "monto": "23,80", "moneda": "USD"})
    html = client.get("/credito/").get_data(as_text=True)
    assert "Deuda total en dólares" in html and "US$ 23,80" in html
    assert "Cupo disponible en dólares" in html and "US$ 126,20" in html   # 150 − 23,80
    assert "US$ 150" in html


def test_panel_sin_dolares_no_muestra_seccion(client):
    crear_cuenta(client)
    assert "Tus créditos en dólares" not in client.get("/credito/").get_data(as_text=True)


def test_pago_tarjeta_crea_egreso_vinculado(app, client):
    crear_cuenta(client)
    client.post("/credito/cuentas/1/compras", data={
        "fecha": "2026-10-01", "categoria": "Ropa", "monto": "60000", "cuotas": "3",
    })
    client.post("/credito/cuentas/1/pagos", data={
        "fecha": "2026-10-20", "monto": "20000", "registrar_egreso": "on",
    })
    assert contar(app, "credito_pagos") == 1
    assert contar(app, "movimientos") == 1

    # Al borrar el pago también se borra el egreso que generó
    client.post("/credito/pagos/1/eliminar")
    assert contar(app, "movimientos") == 0


def test_no_se_puede_pagar_mas_que_la_deuda(app, client):
    crear_cuenta(client)
    r = client.post("/credito/cuentas/1/pagos", data={"fecha": "2026-10-20", "monto": "1000"},
                    follow_redirects=True)
    assert "mayor que la deuda" in r.get_data(as_text=True)
    assert contar(app, "credito_pagos") == 0


def test_movimientos_recuerda_tipo_y_fecha(client):
    client.post("/movimientos/", data={
        "tipo": "ingreso", "fecha": "2026-10-03", "categoria": "Sueldo", "monto": "500000",
    })
    html = client.get("/movimientos/").get_data(as_text=True)
    assert 'value="2026-10-03"' in html
    assert 'value="ingreso" selected' in html


def test_ordenar_movimientos(client):
    for fecha, cat, monto in [("2026-10-03", "Sueldo", "900000"), ("2026-10-10", "Alimentación", "15000"),
                              ("2026-10-05", "Vivienda", "350000")]:
        client.post("/movimientos/", data={"tipo": "egreso", "fecha": fecha, "categoria": cat, "monto": monto})

    def orden(url):
        html = client.get(url).get_data(as_text=True)
        return [c for c in ("Sueldo", "Alimentación", "Vivienda") if c in html.split("<tbody>")[1]
                ] and sorted(("Sueldo", "Alimentación", "Vivienda"), key=lambda c: html.split("<tbody>")[1].index(c))

    assert orden("/movimientos/?mes=2026-10") == ["Alimentación", "Vivienda", "Sueldo"]           # fecha ↓
    assert orden("/movimientos/?mes=2026-10&orden=fecha&dir=asc") == ["Sueldo", "Vivienda", "Alimentación"]
    assert orden("/movimientos/?mes=2026-10&orden=monto&dir=desc") == ["Sueldo", "Vivienda", "Alimentación"]
    assert orden("/movimientos/?mes=2026-10&orden=categoria&dir=asc") == ["Alimentación", "Sueldo", "Vivienda"]
    # Se recuerda el último orden elegido
    assert orden("/movimientos/?mes=2026-10") == ["Alimentación", "Sueldo", "Vivienda"]
    # Un valor raro en la URL no rompe nada (ni se usa en el SQL)
    assert client.get("/movimientos/?orden=monto;DROP TABLE movimientos&dir=x").status_code == 200


def test_compras_y_pagos_en_dolares(app, client):
    client.post("/credito/cuentas", data={"nombre": "BCI", "cupo": "1.000.000", "cupo_usd": "100"})
    client.post("/credito/cuentas/1/compras", data={
        "fecha": "2026-10-01", "categoria": "Entretención", "monto": "12,50", "moneda": "USD",
    })
    client.post("/credito/cuentas/1/compras", data={
        "fecha": "2026-10-02", "categoria": "Ropa", "monto": "20000",
    })
    html = client.get("/credito/?cuenta=1").get_data(as_text=True)
    assert "US$ 12,50" in html
    assert "disponible US$ 87,50 de US$ 100" in html
    assert "$20.000" in html  # la deuda en pesos va por separado

    # Pago en dólares: si se registra como egreso, pide cuántos pesos costó
    r = client.post("/credito/cuentas/1/pagos", data={"fecha": "2026-10-20", "monto": "12,50",
                                                      "moneda": "USD", "registrar_egreso": "on"},
                    follow_redirects=True)
    assert "cuántos pesos pagaste" in r.get_data(as_text=True)
    client.post("/credito/cuentas/1/pagos", data={"fecha": "2026-10-20", "monto": "12,50", "moneda": "USD",
                                                  "monto_clp": "12.000", "registrar_egreso": "on"})
    conn = conectar(app.config["DATABASE"])
    assert conn.execute("SELECT monto FROM movimientos").fetchone()[0] == 12000
    assert conn.execute("SELECT monto, moneda FROM credito_pagos").fetchone()[:] == (1250, "USD")
    conn.close()

    # No se puede pagar en dólares más de lo que se debe en dólares
    r = client.post("/credito/cuentas/1/pagos", data={"fecha": "2026-10-21", "monto": "1", "moneda": "USD"},
                    follow_redirects=True)
    assert "deuda en dólares" in r.get_data(as_text=True)


def test_ahorro_deposito_y_retiro(app, client):
    client.post("/ahorro/", data={"tipo": "deposito", "fecha": "2026-10-05",
                                  "monto": "50000", "vincular": "on"})
    assert contar(app, "movimientos") == 1  # el depósito sale de la cuenta

    r = client.post("/ahorro/", data={"tipo": "retiro", "fecha": "2026-10-06", "monto": "90000"},
                    follow_redirects=True)
    assert "No puedes retirar" in r.get_data(as_text=True)
    assert contar(app, "ahorro") == 1


def test_meta_y_tasa_de_ahorro(client):
    client.post("/ahorro/meta", data={"meta": "1.000.000"})
    client.post("/ahorro/tasa", data={"tasa": "4,6"})
    client.post("/ahorro/", data={"tipo": "deposito", "fecha": "2026-10-05", "monto": "1200000"})
    html = client.get("/ahorro/").get_data(as_text=True)
    assert "$1.000.000" in html
    assert "4,6%" in html
    assert "$55.200" in html  # interés en un año: 1.200.000 × 4,6%

    r = client.post("/ahorro/tasa", data={"tasa": "abc"}, follow_redirects=True)
    assert "debe ser un número" in r.get_data(as_text=True)


def test_registrar_interes_del_mes_una_sola_vez(app, client):
    client.post("/ahorro/tasa", data={"tasa": "4,6"})
    client.post("/ahorro/", data={"tipo": "deposito", "fecha": "2026-10-05", "monto": "1000000"})
    client.post("/ahorro/intereses")
    r = client.post("/ahorro/intereses", follow_redirects=True)
    assert "Ya registraste" in r.get_data(as_text=True)
    assert contar(app, "ahorro") == 2
    assert contar(app, "movimientos") == 0  # el interés no sale de la cuenta principal


def test_exportar_excel(app, client):
    from io import BytesIO

    from openpyxl import load_workbook

    app.test_cli_runner().invoke(args=["seed"])
    r = client.get("/exportar")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    libro = load_workbook(BytesIO(r.data))
    assert libro.sheetnames == ["Resumen", "Movimientos", "Crédito - compras", "Crédito - pagos", "Ahorro"]
    assert libro["Movimientos"].max_row > 10
    assert libro["Crédito - compras"]["A2"].value in ("Falabella", "BCI")


def test_seed_no_mezcla_con_datos_existentes(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed"]).exit_code == 0
    assert contar(app, "movimientos") > 0
    # Segunda vez: la base ya tiene datos, debe negarse
    assert runner.invoke(args=["seed"]).exit_code != 0


def test_resumen_navega_por_meses(client):
    from datetime import date
    from gestor.utils import mover_mes
    actual = date.today().strftime("%Y-%m")
    anterior = mover_mes(actual, -1)

    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": f"{anterior}-05",
                                       "categoria": "Sueldo", "monto": "900000"})
    client.post("/movimientos/", data={"tipo": "egreso", "fecha": f"{actual}-01",
                                       "categoria": "Vivienda", "monto": "300000"})

    html = client.get("/").get_data(as_text=True)
    assert 'aria-label="Mes siguiente"' not in html          # no se puede ir al futuro
    assert "$600.000" in html                                # saldo actual: 900.000 − 300.000

    html = client.get(f"/?mes={anterior}").get_data(as_text=True)
    assert "$900.000" in html                                # saldo al cierre del mes anterior
    assert "Vivienda" not in html                            # el egreso es del mes siguiente
    assert "al cierre de" in html and "Ir al mes actual" in html


def test_resumen_limites_de_meses(client):
    html = client.get("/?mes=2026-01").get_data(as_text=True)
    assert "enero 2026" in html and 'aria-label="Mes anterior"' not in html
    assert "enero 2026" in client.get("/?mes=2025-06").get_data(as_text=True)   # antes de enero 2026 → enero
    assert 'aria-label="Mes siguiente"' not in client.get("/?mes=2099-01").get_data(as_text=True)


def test_exportar_excel_del_mes_que_se_ve(client):
    from io import BytesIO

    from openpyxl import load_workbook

    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-09-05",
                                       "categoria": "Sueldo", "monto": "900000"})
    client.post("/movimientos/", data={"tipo": "egreso", "fecha": "2026-10-03",
                                       "categoria": "Vivienda", "monto": "300000"})

    html = client.get("/?mes=2026-09").get_data(as_text=True)
    assert 'href="/exportar?mes=2026-09"' in html and "Exportar Septiembre a Excel" in html

    r = client.get("/exportar?mes=2026-09")
    assert "gastos-2026-09.xlsx" in r.headers["Content-Disposition"]
    libro = load_workbook(BytesIO(r.data))
    assert "septiembre 2026" in libro["Resumen"]["A1"].value
    movimientos = [f for f in libro["Movimientos"].iter_rows(min_row=2, values_only=True)]
    assert len(movimientos) == 1 and movimientos[0][2] == "Sueldo"     # solo los de septiembre
    resumen = {f[0]: f[1] for f in libro["Resumen"].iter_rows(min_row=3, values_only=True) if f[0]}
    assert resumen["Saldo en cuenta"] == 900000                        # al cierre de septiembre
