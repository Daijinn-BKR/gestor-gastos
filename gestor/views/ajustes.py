"""Ajustes: color de acento, fondo de pantalla y respaldo de datos (exportar/importar).

La imagen se guarda en la carpeta de datos del usuario (junto a gastos.db), nunca
dentro del proyecto: así una imagen personal no termina subida a GitHub."""
from io import BytesIO
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, url_for)

from .. import colores, respaldo
from ..db import get_config, get_config_texto, get_db, set_config

bp = Blueprint("ajustes", __name__, url_prefix="/ajustes")

# Formatos aceptados, reconocidos por sus primeros bytes (no por el nombre del archivo)
FIRMAS = {
    "jpg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],
    "gif": [b"GIF87a", b"GIF89a"],
}
TAMANO_MAXIMO = 15 * 1024 * 1024  # 15 MB
DIFUMINADO_POR_DEFECTO = 6


def _carpeta() -> Path:
    return Path(current_app.config["DATABASE"]).parent


def archivo_fondo() -> Path | None:
    for ext in FIRMAS:
        ruta = _carpeta() / f"fondo.{ext}"
        if ruta.exists():
            return ruta
    return None


def info_fondo() -> dict | None:
    """Datos que usa base.html para dibujar el fondo (None si no hay)."""
    ruta = archivo_fondo()
    if not ruta:
        return None
    return {
        "url": url_for("ajustes.imagen_fondo", v=int(ruta.stat().st_mtime)),  # ?v= evita caché vieja
        "difuminado": get_config("fondo_difuminado", DIFUMINADO_POR_DEFECTO),
    }


def _formato(datos: bytes) -> str | None:
    for ext, firmas in FIRMAS.items():
        if any(datos.startswith(f) for f in firmas):
            if ext == "webp" and datos[8:12] != b"WEBP":
                continue
            return ext
    return None


def color_acento() -> str:
    color = get_config_texto("color_acento", colores.COLOR_POR_DEFECTO)
    return color.upper() if colores.es_color(color) else colores.COLOR_POR_DEFECTO


@bp.get("/")
def inicio():
    return render_template("ajustes.html", fondo=info_fondo(),
                           difuminado=get_config("fondo_difuminado", DIFUMINADO_POR_DEFECTO),
                           color=color_acento(), predefinidos=colores.PREDEFINIDOS,
                           color_por_defecto=colores.COLOR_POR_DEFECTO,
                           carpeta_datos=str(_carpeta()))


# ── Respaldo: exportar e importar todos los datos ───────────────────────

@bp.get("/respaldo")
def exportar_respaldo():
    """Descarga directa (modo navegador). En la app de escritorio se usa main.Api."""
    return send_file(BytesIO(respaldo.generar_respaldo(get_db(), _carpeta())),
                     mimetype="application/zip", as_attachment=True,
                     download_name=respaldo.nombre_archivo())


@bp.post("/respaldo/importar")
def importar_respaldo():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Elige el archivo de respaldo.", "error")
        return redirect(url_for(".inicio"))
    try:
        copia = respaldo.importar_respaldo(get_db(), archivo.read(), _carpeta(), _formato)
    except respaldo.ErrorRespaldo as e:
        flash(str(e), "error")
        return redirect(url_for(".inicio"))
    detalle = f" Tus datos anteriores quedaron guardados en {copia.name}." if copia else ""
    flash("Datos importados." + detalle, "ok")
    return redirect(url_for(".inicio"))


@bp.post("/color")
def cambiar_color():
    color = (request.form.get("color") or "").strip()
    if not colores.es_color(color):
        flash("Color no válido.", "error")
        return redirect(url_for(".inicio"))
    set_config("color_acento", color.upper())
    flash("Color actualizado.", "ok")
    return redirect(url_for(".inicio"))


@bp.post("/color/restablecer")
def restablecer_color():
    set_config("color_acento", colores.COLOR_POR_DEFECTO)
    flash("Color restablecido.", "ok")
    return redirect(url_for(".inicio"))


@bp.get("/fondo")
def imagen_fondo():
    ruta = archivo_fondo()
    if not ruta:
        abort(404)
    return send_file(ruta, max_age=0)


@bp.post("/fondo")
def subir_fondo():
    archivo = request.files.get("imagen")
    if not archivo or not archivo.filename:
        flash("Elige una imagen.", "error")
        return redirect(url_for(".inicio"))
    datos = archivo.read(TAMANO_MAXIMO + 1)
    if len(datos) > TAMANO_MAXIMO:
        flash("La imagen es muy grande (máximo 15 MB).", "error")
        return redirect(url_for(".inicio"))
    ext = _formato(datos)
    if not ext:
        flash("Ese archivo no es una imagen válida. Usa JPG, PNG, WEBP o GIF.", "error")
        return redirect(url_for(".inicio"))

    _borrar_fondo()
    (_carpeta() / f"fondo.{ext}").write_bytes(datos)
    flash("Fondo de pantalla actualizado.", "ok")
    return redirect(url_for(".inicio"))


@bp.post("/fondo/difuminado")
def cambiar_difuminado():
    try:
        valor = max(0, min(30, int(request.form.get("difuminado", DIFUMINADO_POR_DEFECTO))))
    except ValueError:
        valor = DIFUMINADO_POR_DEFECTO
    set_config("fondo_difuminado", valor)
    flash("Difuminado actualizado.", "ok")
    return redirect(url_for(".inicio"))


@bp.post("/fondo/quitar")
def quitar_fondo():
    _borrar_fondo()
    flash("Fondo de pantalla quitado.", "ok")
    return redirect(url_for(".inicio"))


def _borrar_fondo():
    for ext in FIRMAS:
        (_carpeta() / f"fondo.{ext}").unlink(missing_ok=True)
