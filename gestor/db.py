"""Conexión a SQLite y comandos de línea de comandos (init-db, seed)."""
import sqlite3
from datetime import datetime
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext

SCHEMA = Path(__file__).with_name("schema.sql")


def get_db() -> sqlite3.Connection:
    """Devuelve la conexión de la petición actual (la crea si no existe)."""
    if "db" not in g:
        g.db = conectar(current_app.config["DATABASE"])
    return g.db


def conectar(ruta: str) -> sqlite3.Connection:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


VERSION_ESQUEMA = 4


def init_db(conn: sqlite3.Connection):
    """Crea las tablas que falten y actualiza bases de versiones anteriores."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    es_antigua = version < VERSION_ESQUEMA and _existe_tabla(conn, "movimientos")
    if es_antigua and _tiene_datos(conn):
        respaldar(conn)

    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    if es_antigua:
        # Cada paso revisa qué falta antes de cambiar algo, así que se puede repetir sin riesgo.
        _migrar_a_v2(conn)
        _migrar_a_v3(conn)
        _migrar_a_v4(conn)
    conn.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
    conn.commit()


def _existe_tabla(conn, tabla: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabla,)
    ).fetchone() is not None


def _columnas(conn, tabla: str) -> set[str]:
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})")}


def _tiene_datos(conn) -> bool:
    tablas = ["movimientos", "credito_compras", "credito_pagos", "ahorro", "config"]
    return any(
        _existe_tabla(conn, t) and conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()
        for t in tablas
    )


def respaldar(conn) -> Path | None:
    """Copia la base a 'gastos.respaldo-AAAAMMDD-HHMMSS.db' en la misma carpeta."""
    archivo = conn.execute("PRAGMA database_list").fetchone()[2]
    if not archivo:  # base en memoria
        return None
    origen = Path(archivo)
    destino = origen.with_name(f"{origen.stem}.respaldo-{datetime.now():%Y%m%d-%H%M%S}.db")
    copia = sqlite3.connect(destino)
    conn.backup(copia)
    copia.close()
    return destino


def _migrar_a_v2(conn):
    """v1 → v2: varias cuentas de crédito e interés por compra.

    Las compras y pagos existentes se asignan a una cuenta 'Tarjeta principal'
    con el cupo que estaba configurado antes."""
    if "cuenta_id" not in _columnas(conn, "credito_compras"):
        conn.execute("ALTER TABLE credito_compras ADD COLUMN cuenta_id "
                     "INTEGER REFERENCES credito_cuentas(id) ON DELETE CASCADE")
    if "interes" not in _columnas(conn, "credito_compras"):
        conn.execute("ALTER TABLE credito_compras ADD COLUMN interes "
                     "REAL NOT NULL DEFAULT 0 CHECK (interes >= 0)")
    if "cuenta_id" not in _columnas(conn, "credito_pagos"):
        conn.execute("ALTER TABLE credito_pagos ADD COLUMN cuenta_id "
                     "INTEGER REFERENCES credito_cuentas(id) ON DELETE CASCADE")

    cupo = conn.execute("SELECT valor FROM config WHERE clave = 'cupo_credito'").fetchone()
    sin_cuenta = conn.execute(
        "SELECT 1 FROM credito_compras WHERE cuenta_id IS NULL "
        "UNION SELECT 1 FROM credito_pagos WHERE cuenta_id IS NULL LIMIT 1"
    ).fetchone()
    hay_cuentas = conn.execute("SELECT 1 FROM credito_cuentas LIMIT 1").fetchone()

    if sin_cuenta or (cupo and not hay_cuentas):
        cur = conn.execute(
            "INSERT INTO credito_cuentas (nombre, cupo) VALUES ('Tarjeta principal', ?)",
            (int(cupo[0]) if cupo else 1_000_000,),
        )
        conn.execute("UPDATE credito_compras SET cuenta_id = ? WHERE cuenta_id IS NULL", (cur.lastrowid,))
        conn.execute("UPDATE credito_pagos SET cuenta_id = ? WHERE cuenta_id IS NULL", (cur.lastrowid,))
    conn.execute("DELETE FROM config WHERE clave = 'cupo_credito'")


def _agregar_columna(conn, tabla: str, columna: str, definicion: str):
    if columna not in _columnas(conn, tabla):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _migrar_a_v3(conn):
    """v2 → v3: compras y pagos internacionales en dólares."""
    _agregar_columna(conn, "credito_cuentas", "cupo_usd",
                     "INTEGER NOT NULL DEFAULT 0 CHECK (cupo_usd >= 0)")
    _agregar_columna(conn, "credito_compras", "moneda",
                     "TEXT NOT NULL DEFAULT 'CLP' CHECK (moneda IN ('CLP', 'USD'))")
    _agregar_columna(conn, "credito_pagos", "moneda",
                     "TEXT NOT NULL DEFAULT 'CLP' CHECK (moneda IN ('CLP', 'USD'))")
    _agregar_columna(conn, "credito_pagos", "monto_clp", "INTEGER")


def _migrar_a_v4(conn):
    """v3 → v4: día de facturación de cada crédito."""
    _agregar_columna(conn, "credito_cuentas", "dia_facturacion",
                     "INTEGER CHECK (dia_facturacion BETWEEN 1 AND 31)")


def get_config(clave: str, por_defecto: float = 0) -> float:
    fila = get_db().execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    if not fila:
        return por_defecto
    valor = float(fila["valor"])
    return int(valor) if valor.is_integer() else valor


def get_config_texto(clave: str, por_defecto: str = "") -> str:
    fila = get_db().execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else por_defecto


def set_config(clave: str, valor):
    conn = get_db()
    conn.execute(
        "INSERT INTO config (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (clave, str(valor)),
    )
    conn.commit()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Crea las tablas (no borra datos existentes)."""
    init_db(get_db())
    click.echo(f"Base de datos lista en {current_app.config['DATABASE']}")


@click.command("seed")
@with_appcontext
@click.option("--force", is_flag=True, help="Agregar datos aunque la base ya tenga registros.")
def seed_command(force):
    """Llena la base con datos ficticios para probar la app."""
    from .seed import cargar_datos_demo

    conn = get_db()
    init_db(conn)
    hay_datos = conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
    if hay_datos and not force:
        raise click.ClickException(
            "La base ya tiene datos. Para no mezclar datos de ejemplo con los tuyos, "
            "usa otra base (GESTOR_DB=demo.db) o agrega --force."
        )
    cargar_datos_demo(conn)
    click.echo(f"Datos de ejemplo cargados en {current_app.config['DATABASE']}")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)
    with app.app_context():
        init_db(get_db())
