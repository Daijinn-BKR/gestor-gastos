"""Ajustes: color de acento, fondo de pantalla y respaldo de datos (exportar/importar).

La imagen se guarda en la carpeta de datos del usuario (junto a gastos.db), nunca
dentro del proyecto: así una imagen personal no termina subida a GitHub."""
import shutil
import sqlite3
from io import BytesIO
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, session, url_for)

from .. import colores, respaldo, ubicacion
from ..db import (close_db, conectar, get_config, get_config_texto, get_db,
                  init_db, respaldar, set_config)

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


TEMAS = {"auto": "Automático", "claro": "Claro", "oscuro": "Oscuro"}


def tema() -> str:
    """'auto' (sigue a Windows), 'claro' u 'oscuro'."""
    valor = get_config_texto("tema", "auto")
    return valor if valor in TEMAS else "auto"


@bp.post("/tema")
def cambiar_tema():
    valor = request.form.get("tema")
    if valor not in TEMAS:
        flash("Tema no válido.", "error")
    else:
        set_config("tema", valor)
    return redirect(url_for(".inicio"))


def color_acento() -> str:
    color = get_config_texto("color_acento", colores.COLOR_POR_DEFECTO)
    return color.upper() if colores.es_color(color) else colores.COLOR_POR_DEFECTO


@bp.get("/")
def inicio():
    return render_template("ajustes.html", fondo=info_fondo(),
                           difuminado=get_config("fondo_difuminado", DIFUMINADO_POR_DEFECTO),
                           color=color_acento(), predefinidos=colores.PREDEFINIDOS,
                           temas=TEMAS,
                           color_por_defecto=colores.COLOR_POR_DEFECTO,
                           carpeta_datos=str(_carpeta()),
                           carpeta_por_defecto=current_app.config["CARPETA_POR_DEFECTO"],
                           carpeta_personalizada=_carpeta() != Path(current_app.config["CARPETA_POR_DEFECTO"]),
                           carpeta_pendiente=session.get("carpeta_pendiente"),
                           equipo=ubicacion.nombre_equipo())


# ── Carpeta de datos (para sincronizar con OneDrive, Google Drive…) ─────

def _copiar_fondo(origen: Path, destino: Path, reemplazar: bool):
    fondos = [origen / f"fondo.{ext}" for ext in FIRMAS if (origen / f"fondo.{ext}").exists()]
    if not fondos:
        return
    existentes = [destino / f"fondo.{ext}" for ext in FIRMAS if (destino / f"fondo.{ext}").exists()]
    if existentes and not reemplazar:
        return
    for archivo in existentes:
        archivo.unlink()
    shutil.copy2(fondos[0], destino / fondos[0].name)


def _copiar_base(destino_db: Path):
    """Copia la base actual a destino_db de forma segura aunque esté abierta."""
    copia = sqlite3.connect(destino_db)
    try:
        get_db().backup(copia)
    finally:
        copia.close()


@bp.post("/carpeta")
def cambiar_carpeta():
    texto = (request.form.get("carpeta") or "").strip().strip('"')
    accion = request.form.get("accion")          # None, "usar" o "reemplazar"
    volver = redirect(url_for(".inicio") + "#sincronizar")
    if not texto:
        flash("Escribe o elige una carpeta.", "error")
        return volver
    destino = Path(texto).expanduser()
    if not destino.is_absolute():
        flash("Escribe la ruta completa de la carpeta, por ejemplo C:\\Users\\tu-usuario\\OneDrive\\GestorGastos.", "error")
        return volver
    if not destino.is_dir():
        flash(f"La carpeta {destino} no existe. Créala primero (por ejemplo dentro de OneDrive).", "error")
        return volver
    if not ubicacion.es_escribible(destino):
        flash("No se puede guardar en esa carpeta (sin permiso de escritura).", "error")
        return volver

    origen = _carpeta()
    nueva_db = destino / ubicacion.NOMBRE_DB
    if destino.resolve() == origen.resolve():
        session.pop("carpeta_pendiente", None)
        flash("Tus datos ya están en esa carpeta.", "ok")
        return volver

    if nueva_db.exists() and accion not in ("usar", "reemplazar"):
        # La carpeta ya tiene datos (ej. de otro computador): el usuario decide qué hacer.
        session["carpeta_pendiente"] = str(destino)
        return volver

    if nueva_db.exists() and accion == "usar":
        try:
            respaldo._validar_base(nueva_db)
        except respaldo.ErrorRespaldo as e:
            flash(f"No se pueden usar los datos de esa carpeta: {e}", "error")
            return volver
        _copiar_fondo(origen, destino, reemplazar=False)
        mensaje = "Listo: ahora usas los datos de esa carpeta."
    else:
        if nueva_db.exists():                     # reemplazar: antes se guarda una copia
            existente = conectar(str(nueva_db))
            try:
                respaldar(existente)
            finally:
                existente.close()
        _copiar_base(nueva_db)
        _copiar_fondo(origen, destino, reemplazar=True)
        mensaje = "Listo: tus datos se copiaron a la nueva carpeta y desde ahora se guardan ahí."

    # Cambiar a la nueva carpeta
    ubicacion.liberar(origen)
    close_db()
    conn = conectar(str(nueva_db))
    try:
        init_db(conn)                             # actualiza bases de versiones antiguas
    finally:
        conn.close()
    por_defecto = Path(current_app.config["CARPETA_POR_DEFECTO"])
    ubicacion.guardar_ubicacion(Path(current_app.config["ARCHIVO_UBICACION"]),
                                None if destino.resolve() == por_defecto.resolve() else destino)
    current_app.config.update(DATABASE=str(nueva_db), AVISO_CARPETA=None)
    ubicacion.latido(destino, forzar=True)
    session.pop("carpeta_pendiente", None)
    flash(mensaje + f" (La copia anterior sigue en {origen}.)", "ok")
    return volver


@bp.post("/carpeta/cancelar")
def cancelar_carpeta():
    session.pop("carpeta_pendiente", None)
    return redirect(url_for(".inicio") + "#sincronizar")


@bp.post("/latido")
def latido():
    """La página llama aquí cada minuto para avisar que la app sigue abierta."""
    return "", 204


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
