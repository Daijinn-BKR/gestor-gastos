"""Exportar e importar todos los datos en un solo archivo .zip.

El archivo contiene:
- gastos.db   copia de la base (movimientos, créditos, ahorro y ajustes como el color)
- fondo.*     la imagen de fondo, si hay una
- info.json   fecha y versión, solo informativo

Al importar se valida todo antes de tocar nada y se guarda una copia automática de los
datos actuales (gastos.respaldo-FECHA.db), así un error nunca hace perder información.
"""
import json
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from .db import VERSION_ESQUEMA, init_db, respaldar

FIRMA_SQLITE = b"SQLite format 3\x00"
TABLAS_REQUERIDAS = {"movimientos", "ahorro", "config"}
TAMANO_MAXIMO_DB = 200 * 1024 * 1024
EXTENSIONES_FONDO = ("jpg", "png", "webp", "gif")


class ErrorRespaldo(ValueError):
    """Error con un mensaje apto para mostrar al usuario."""


def nombre_archivo(hoy: date | None = None) -> str:
    return f"gestor-gastos-respaldo-{(hoy or date.today()).isoformat()}.zip"


# ── Exportar ─────────────────────────────────────────────────────────────

def generar_respaldo(conn: sqlite3.Connection, carpeta_datos: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        copia_db = Path(tmp) / "gastos.db"
        destino = sqlite3.connect(copia_db)
        conn.backup(destino)            # copia consistente aunque la base esté abierta
        destino.close()

        salida = BytesIO()
        with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(copia_db, "gastos.db")
            for ext in EXTENSIONES_FONDO:
                fondo = carpeta_datos / f"fondo.{ext}"
                if fondo.exists():
                    zf.write(fondo, f"fondo.{ext}")
                    break
            zf.writestr("info.json", json.dumps({
                "app": "gestor-gastos",
                "version_esquema": VERSION_ESQUEMA,
                "exportado": datetime.now().isoformat(timespec="seconds"),
            }, indent=2))
        return salida.getvalue()


# ── Importar ─────────────────────────────────────────────────────────────

def _leer_archivo(datos: bytes) -> tuple[bytes, tuple[str, bytes] | None]:
    """Devuelve (bytes de la base, (extensión, bytes) del fondo o None)."""
    if datos.startswith(FIRMA_SQLITE):          # también se acepta un .db suelto
        return datos, None
    if not zipfile.is_zipfile(BytesIO(datos)):
        raise ErrorRespaldo("El archivo no es un respaldo del Gestor de gastos (.zip o .db).")

    with zipfile.ZipFile(BytesIO(datos)) as zf:
        nombres = {i.filename: i for i in zf.infolist()}
        if "gastos.db" not in nombres:
            raise ErrorRespaldo("El .zip no contiene gastos.db. ¿Es un respaldo de esta app?")
        if nombres["gastos.db"].file_size > TAMANO_MAXIMO_DB:
            raise ErrorRespaldo("La base de datos del respaldo es demasiado grande.")
        db = zf.read("gastos.db")

        fondo = None
        for ext in EXTENSIONES_FONDO:
            info = nombres.get(f"fondo.{ext}")
            if info and info.file_size <= 15 * 1024 * 1024:
                fondo = (ext, zf.read(info))
                break
    return db, fondo


def _validar_base(ruta: Path):
    try:
        conn = sqlite3.connect(ruta)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ErrorRespaldo("El respaldo está dañado.")
            tablas = {f[0] for f in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        raise ErrorRespaldo("El respaldo está dañado o no es una base de datos válida.") from None
    if not TABLAS_REQUERIDAS <= tablas:
        raise ErrorRespaldo("Esa base de datos no es del Gestor de gastos.")
    if version > VERSION_ESQUEMA:
        raise ErrorRespaldo("El respaldo es de una versión más nueva de la app. Actualiza la app primero.")


def importar_respaldo(conn: sqlite3.Connection, datos: bytes, carpeta_datos: Path,
                      formato_imagen) -> Path | None:
    """Reemplaza todos los datos por los del respaldo. Devuelve la ruta de la copia previa.

    `formato_imagen(bytes)` valida la imagen de fondo (devuelve la extensión o None)."""
    db, fondo = _leer_archivo(datos)

    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "importado.db"
        ruta.write_bytes(db)
        _validar_base(ruta)                      # si algo falla, aquí se detiene sin tocar nada

        copia_previa = respaldar(conn)           # copia de seguridad de los datos actuales
        origen = sqlite3.connect(ruta)
        try:
            conn.commit()
            origen.backup(conn)                  # reemplaza el contenido de la base abierta
        finally:
            origen.close()
    init_db(conn)                                # actualiza respaldos de versiones antiguas

    if fondo and formato_imagen(fondo[1]) == fondo[0]:
        for ext in EXTENSIONES_FONDO:
            (carpeta_datos / f"fondo.{ext}").unlink(missing_ok=True)
        (carpeta_datos / f"fondo.{fondo[0]}").write_bytes(fondo[1])
    return copia_previa
