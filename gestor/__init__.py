"""Gestor de gastos personales: movimientos, tarjeta de crédito y ahorro."""
import os
import secrets
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from . import db
from .rutas import carpeta_datos
from .utils import clp, fecha_corta, nombre_mes, pct, usd

BASE_DIR = Path(__file__).resolve().parent.parent


def ruta_db() -> str:
    """Por defecto la base vive en la carpeta de datos del usuario (fuera del proyecto).
    Se puede cambiar con la variable de entorno GESTOR_DB."""
    personalizada = os.environ.get("GESTOR_DB")
    if not personalizada:
        return str(carpeta_datos() / "gastos.db")
    ruta = Path(personalizada).expanduser()
    if not ruta.is_absolute():
        ruta = carpeta_datos() / ruta
    return str(ruta)


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv(BASE_DIR / ".env")

    app = Flask(__name__)
    app.config.from_mapping(
        # Solo se usa para los mensajes de confirmación; una clave nueva por sesión basta.
        SECRET_KEY=os.environ.get("GESTOR_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=ruta_db(),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    app.jinja_env.filters["clp"] = clp
    app.jinja_env.filters["fecha"] = fecha_corta
    app.jinja_env.filters["nombre_mes"] = nombre_mes
    app.jinja_env.filters["pct"] = pct
    app.jinja_env.filters["usd"] = usd

    app.config.setdefault("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)  # subida del fondo de pantalla

    from .views import ahorro, ajustes, credito, movimientos, resumen

    @app.context_processor
    def variables_globales():
        return {"hoy": date.today().isoformat(), "fondo": ajustes.info_fondo()}

    for modulo in (resumen, movimientos, credito, ahorro, ajustes):
        app.register_blueprint(modulo.bp)

    return app
