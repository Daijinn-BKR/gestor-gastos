"""Una base creada con la versión 1 (una sola tarjeta) debe actualizarse sin perder datos."""
import sqlite3

from gestor import create_app
from gestor.db import conectar

ESQUEMA_V1 = """
CREATE TABLE movimientos (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
    tipo TEXT NOT NULL, categoria TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '', monto INTEGER NOT NULL);
CREATE TABLE credito_compras (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
    categoria TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '', monto INTEGER NOT NULL,
    cuotas INTEGER NOT NULL DEFAULT 1);
CREATE TABLE credito_pagos (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '', monto INTEGER NOT NULL,
    movimiento_id INTEGER REFERENCES movimientos(id) ON DELETE SET NULL);
CREATE TABLE ahorro (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, tipo TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '', monto INTEGER NOT NULL, movimiento_id INTEGER);
CREATE TABLE config (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
INSERT INTO movimientos (fecha, tipo, categoria, monto) VALUES ('2026-10-01', 'ingreso', 'Sueldo', 900000);
INSERT INTO credito_compras (fecha, categoria, monto, cuotas) VALUES ('2026-10-02', 'Ropa', 45000, 3);
INSERT INTO credito_pagos (fecha, monto) VALUES ('2026-10-20', 15000);
INSERT INTO config VALUES ('cupo_credito', '750000'), ('meta_ahorro', '500000');
"""


def test_migra_base_v1_con_respaldo(tmp_path):
    ruta = tmp_path / "gastos.db"
    conn = sqlite3.connect(ruta)
    conn.executescript(ESQUEMA_V1)
    conn.close()

    app = create_app({"TESTING": True, "DATABASE": str(ruta)})

    conn = conectar(str(ruta))
    cuenta = conn.execute("SELECT * FROM credito_cuentas").fetchone()
    assert (cuenta["nombre"], cuenta["cupo"]) == ("Tarjeta principal", 750000)
    assert conn.execute("SELECT cuenta_id, interes FROM credito_compras").fetchone()[:] == (cuenta["id"], 0)
    assert conn.execute("SELECT cuenta_id FROM credito_pagos").fetchone()[0] == cuenta["id"]
    assert conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0] == 1
    assert conn.execute("SELECT valor FROM config WHERE clave = 'meta_ahorro'").fetchone()[0] == "500000"
    assert conn.execute("SELECT 1 FROM config WHERE clave = 'cupo_credito'").fetchone() is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("SELECT moneda FROM credito_compras").fetchone()[0] == "CLP"
    conn.close()

    respaldos = list(tmp_path.glob("gastos.respaldo-*.db"))
    assert len(respaldos) == 1
    viejo = sqlite3.connect(respaldos[0])
    assert viejo.execute("SELECT COUNT(*) FROM credito_compras").fetchone()[0] == 1
    viejo.close()

    # La app funciona con la base migrada, y abrirla de nuevo no repite la migración
    assert "Tarjeta principal" in app.test_client().get("/credito/").get_data(as_text=True)
    create_app({"TESTING": True, "DATABASE": str(ruta)})
    assert len(list(tmp_path.glob("gastos.respaldo-*.db"))) == 1


def test_base_nueva_no_crea_respaldo_ni_tarjeta(tmp_path):
    create_app({"TESTING": True, "DATABASE": str(tmp_path / "nueva.db")})
    conn = conectar(str(tmp_path / "nueva.db"))
    assert conn.execute("SELECT COUNT(*) FROM credito_cuentas").fetchone()[0] == 0
    conn.close()
    assert not list(tmp_path.glob("*.respaldo-*"))


ESQUEMA_V2_EXTRA = """
CREATE TABLE credito_cuentas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
    cupo INTEGER NOT NULL DEFAULT 0);
ALTER TABLE credito_compras ADD COLUMN cuenta_id INTEGER REFERENCES credito_cuentas(id) ON DELETE CASCADE;
ALTER TABLE credito_compras ADD COLUMN interes REAL NOT NULL DEFAULT 0;
ALTER TABLE credito_pagos ADD COLUMN cuenta_id INTEGER REFERENCES credito_cuentas(id) ON DELETE CASCADE;
INSERT INTO credito_cuentas (nombre, cupo) VALUES ('Falabella', 750000);
UPDATE credito_compras SET cuenta_id = 1;
UPDATE credito_pagos SET cuenta_id = 1;
DELETE FROM config WHERE clave = 'cupo_credito';
PRAGMA user_version = 2;
"""


def test_migra_base_v2_a_v3_dolares(tmp_path):
    """La base que ya tenía varias cuentas (v2) gana soporte de dólares sin perder nada."""
    ruta = tmp_path / "gastos.db"
    conn = sqlite3.connect(ruta)
    conn.executescript(ESQUEMA_V1 + ESQUEMA_V2_EXTRA)
    conn.close()

    app = create_app({"TESTING": True, "DATABASE": str(ruta)})
    conn = conectar(str(ruta))
    cuenta = conn.execute("SELECT * FROM credito_cuentas").fetchone()
    assert (cuenta["nombre"], cuenta["cupo"], cuenta["cupo_usd"]) == ("Falabella", 750000, 0)
    assert conn.execute("SELECT COUNT(*) FROM credito_cuentas").fetchone()[0] == 1  # no crea otra
    assert conn.execute("SELECT moneda FROM credito_pagos").fetchone()[0] == "CLP"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    conn.close()
    assert len(list(tmp_path.glob("gastos.respaldo-*.db"))) == 1
    assert "Falabella" in app.test_client().get("/credito/").get_data(as_text=True)
