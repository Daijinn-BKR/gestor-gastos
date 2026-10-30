"""Genera datos FICTICIOS para probar la app o tomar capturas para el README."""
import random
from datetime import date, timedelta

from .utils import mover_mes

GASTOS = [
    ("Alimentación", "Supermercado", 25_000, 85_000),
    ("Alimentación", "Feria", 8_000, 20_000),
    ("Transporte", "Carga tarjeta bip!", 10_000, 20_000),
    ("Transporte", "Bencina", 25_000, 45_000),
    ("Servicios", "Luz", 18_000, 35_000),
    ("Servicios", "Internet", 22_000, 22_000),
    ("Entretención", "Cine", 7_000, 15_000),
    ("Salud", "Farmacia", 5_000, 30_000),
]

# (nombre, cupo en pesos, cupo internacional en centavos de dólar)
CUENTAS = [("Falabella", 800_000, 0), ("BCI", 1_200_000, 50_000)]

# (cuenta, categoría, descripción, monto, cuotas, interés mensual %)
COMPRAS = [
    (0, "Ropa", "Zapatillas", 59_990, 3, 0),
    (1, "Educación", "Curso online", 120_000, 6, 0),
    (0, "Entretención", "Audífonos", 34_990, 1, 0),
    (1, "Vivienda", "Microondas", 89_990, 12, 2.1),
]


def _dia(mes: str, dia: int) -> str:
    anio, num = map(int, mes.split("-"))
    primero = date(anio, num, 1)
    fecha = primero + timedelta(days=min(dia, 28) - 1)
    return min(fecha, date.today()).isoformat()


def cargar_datos_demo(conn, meses: int = 3, semilla: int = 42):
    rnd = random.Random(semilla)
    mes_actual = date.today().strftime("%Y-%m")

    for i in range(meses - 1, -1, -1):
        mes = mover_mes(mes_actual, -i)
        conn.execute(
            "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
            "VALUES (?, 'ingreso', 'Sueldo', 'Sueldo mensual', 950000)",
            (_dia(mes, 1),),
        )
        conn.execute(
            "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
            "VALUES (?, 'egreso', 'Vivienda', 'Arriendo', 350000)",
            (_dia(mes, 3),),
        )
        for _ in range(rnd.randint(8, 12)):
            cat, desc, minimo, maximo = rnd.choice(GASTOS)
            monto = rnd.randint(minimo // 100, maximo // 100) * 100
            conn.execute(
                "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
                "VALUES (?, 'egreso', ?, ?, ?)",
                (_dia(mes, rnd.randint(2, 28)), cat, desc, monto),
            )
        # Depósito mensual al ahorro, reflejado como egreso
        cur = conn.execute(
            "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
            "VALUES (?, 'egreso', 'Ahorro', 'Depósito a ahorro', 80000)",
            (_dia(mes, 5),),
        )
        conn.execute(
            "INSERT INTO ahorro (fecha, tipo, descripcion, monto, movimiento_id) "
            "VALUES (?, 'deposito', 'Ahorro mensual', 80000, ?)",
            (_dia(mes, 5), cur.lastrowid),
        )

    ids = [conn.execute("INSERT INTO credito_cuentas (nombre, cupo, cupo_usd) VALUES (?, ?, ?)", c).lastrowid
           for c in CUENTAS]
    for j, (cuenta, cat, desc, monto, cuotas, interes) in enumerate(COMPRAS):
        mes = mover_mes(mes_actual, -(len(COMPRAS) - 1 - j) // 2)
        conn.execute(
            "INSERT INTO credito_compras (cuenta_id, fecha, categoria, descripcion, monto, cuotas, interes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ids[cuenta], _dia(mes, 10 + j * 4), cat, desc, monto, cuotas, interes),
        )

    # Compras internacionales en dólares (montos en centavos)
    for dia, desc, centavos in [(4, "Suscripción streaming", 1_299), (18, "Juego en tienda online", 5_999)]:
        conn.execute(
            "INSERT INTO credito_compras (cuenta_id, fecha, categoria, descripcion, monto, cuotas, moneda) "
            "VALUES (?, ?, 'Entretención', ?, ?, 1, 'USD')",
            (ids[1], _dia(mes_actual, dia), desc, centavos),
        )

    cur = conn.execute(
        "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
        "VALUES (?, 'egreso', 'Tarjeta de crédito', 'Pago Falabella', 60000)",
        (_dia(mes_actual, 6),),
    )
    conn.execute(
        "INSERT INTO credito_pagos (cuenta_id, fecha, descripcion, monto, movimiento_id) "
        "VALUES (?, ?, 'Pago mensual', 60000, ?)",
        (ids[0], _dia(mes_actual, 6), cur.lastrowid),
    )

    conn.executemany(
        "INSERT INTO config (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        [("meta_ahorro", "1000000"), ("tasa_ahorro", "4.6"),
         ("interes_modo", "diario"), ("interes_desde", date.today().isoformat())],
    )
    conn.commit()
