"""Gestor de gastos personales: movimientos, tarjeta de crédito y ahorro."""
import os
import secrets
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from . import colores, db, ubicacion
from .rutas import carpeta_datos
from .utils import clp, fecha_corta, nombre_mes, pct, usd

BASE_DIR = Path(__file__).resolve().parent.parent


def ruta_db(archivo_ubicacion: Path | None = None) -> str:
    """Por defecto la base vive en la carpeta de datos del usuario (fuera del proyecto),
    o en la carpeta elegida en Ajustes (ej. OneDrive). La variable de entorno GESTOR_DB
    tiene prioridad (la usan el modo demo y los tests)."""
    personalizada = os.environ.get("GESTOR_DB")
    if not personalizada:
        ruta, _ = ubicacion.resolver(archivo_ubicacion or ubicacion.archivo_ubicacion(), carpeta_datos())
        return str(ruta)
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
        ARCHIVO_UBICACION=str(ubicacion.archivo_ubicacion()),
        CARPETA_POR_DEFECTO=str(carpeta_datos()),
        AVISO_CARPETA=None,
    )
    if test_config:
        app.config.update(test_config)
    if "DATABASE" not in app.config:
        if os.environ.get("GESTOR_DB"):
            app.config["DATABASE"] = ruta_db()
        else:
            ruta, aviso = ubicacion.resolver(Path(app.config["ARCHIVO_UBICACION"]),
                                             Path(app.config["CARPETA_POR_DEFECTO"]))
            app.config.update(DATABASE=str(ruta), AVISO_CARPETA=aviso)

    db.init_app(app)

    app.jinja_env.filters["clp"] = clp
    app.jinja_env.filters["fecha"] = fecha_corta
    app.jinja_env.filters["nombre_mes"] = nombre_mes
    app.jinja_env.filters["pct"] = pct
    app.jinja_env.filters["usd"] = usd

    app.config.setdefault("MAX_CONTENT_LENGTH", 256 * 1024 * 1024)  # fondo de pantalla y respaldos

    from .views import ahorro, ajustes, credito, movimientos, resumen

    @app.context_processor
    def variables_globales():
        carpeta = Path(app.config["DATABASE"]).parent
        return {"hoy": date.today().isoformat(), "fondo": ajustes.info_fondo(),
                "css_acento": colores.css(ajustes.color_acento()),
                "tema": ajustes.tema(),
                "aviso_carpeta": app.config.get("AVISO_CARPETA"),
                "otro_equipo": ubicacion.otro_equipo_activo(carpeta),
                "copias_conflicto": ubicacion.copias_en_conflicto(carpeta),
                "carpeta_sincronizada": carpeta != Path(app.config["CARPETA_POR_DEFECTO"])}

    @app.before_request
    def marcar_en_uso():
        ubicacion.latido(Path(app.config["DATABASE"]).parent)

    for modulo in (resumen, movimientos, credito, ahorro, ajustes):
        app.register_blueprint(modulo.bp)

    return app
