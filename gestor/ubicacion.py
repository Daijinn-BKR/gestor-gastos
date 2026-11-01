"""Dónde se guardan los datos, y avisos para usarlos sincronizados (OneDrive, Google Drive…).

- La carpeta elegida se recuerda en `ubicacion.json`, que siempre vive en la carpeta de
  datos por defecto de este computador (%APPDATA%\\GestorGastos). Así cada computador
  sabe dónde buscar, aunque la carpeta sincronizada tenga otra ruta en cada uno.
- `en_uso.json` (dentro de la carpeta de datos) indica qué computador tiene la app abierta.
  Se actualiza cada minuto mientras la app está abierta; si otro computador lo actualizó
  hace poco, se muestra un aviso para no editar en dos lados a la vez.
"""
import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path

from .rutas import carpeta_datos

NOMBRE_DB = "gastos.db"
VIGENCIA_LATIDO = 3 * 60          # segundos: si el otro equipo no da señales en 3 min, se ignora
INTERVALO_LATIDO = 50             # segundos entre escrituras de en_uso.json


def archivo_ubicacion() -> Path:
    return carpeta_datos() / "ubicacion.json"


def leer_ubicacion(archivo: Path) -> Path | None:
    try:
        carpeta = json.loads(archivo.read_text(encoding="utf-8")).get("carpeta")
    except (OSError, ValueError):
        return None
    return Path(carpeta) if carpeta else None


def guardar_ubicacion(archivo: Path, carpeta: Path | None):
    """Guarda la carpeta elegida. None = volver a la carpeta por defecto."""
    if carpeta is None:
        archivo.unlink(missing_ok=True)
        return
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps({"carpeta": str(carpeta)}, ensure_ascii=False, indent=2),
                       encoding="utf-8")


def resolver(archivo: Path, por_defecto: Path) -> tuple[Path, str | None]:
    """Ruta de la base a usar y, si corresponde, un aviso para el usuario.

    Si la carpeta elegida no está disponible (ej. OneDrive todavía no sincroniza o el
    disco no está conectado) se usa la carpeta por defecto y se avisa, en vez de crear
    en silencio una base vacía que haga parecer que se perdieron los datos."""
    elegida = leer_ubicacion(archivo)
    if elegida is None:
        return por_defecto / NOMBRE_DB, None
    if elegida.is_dir():
        return elegida / NOMBRE_DB, None
    return por_defecto / NOMBRE_DB, (
        f"No se encontró tu carpeta de datos ({elegida}). Revisa que OneDrive o Google Drive "
        "esté sincronizado. Mientras tanto se muestran los datos guardados en este computador."
    )


def es_escribible(carpeta: Path) -> bool:
    prueba = carpeta / f".prueba-{os.getpid()}"
    try:
        prueba.write_text("ok")
        prueba.unlink()
        return True
    except OSError:
        return False


# ── Uso en varios computadores ───────────────────────────────────────────

def nombre_equipo() -> str:
    return socket.gethostname() or "este computador"


_ultimo_latido: dict[str, float] = {}


def latido(carpeta: Path, forzar: bool = False):
    """Marca que este computador tiene la app abierta (como máximo una vez por minuto)."""
    clave = str(carpeta)
    ahora = time.time()
    if not forzar and ahora - _ultimo_latido.get(clave, 0) < INTERVALO_LATIDO:
        return
    try:
        (carpeta / "en_uso.json").write_text(json.dumps({
            "equipo": nombre_equipo(), "hora": ahora,
            "desde": datetime.now().isoformat(timespec="seconds"),
        }), encoding="utf-8")
        _ultimo_latido[clave] = ahora
    except OSError:
        pass


def otro_equipo_activo(carpeta: Path) -> str | None:
    """Nombre del otro computador que tiene la app abierta, si dio señales hace poco."""
    try:
        datos = json.loads((carpeta / "en_uso.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if datos.get("equipo") == nombre_equipo():
        return None
    if time.time() - float(datos.get("hora", 0)) > VIGENCIA_LATIDO:
        return None
    return datos.get("equipo") or "otro computador"


def liberar(carpeta: Path):
    """Al cerrar la app: borra la marca si es de este computador."""
    archivo = carpeta / "en_uso.json"
    try:
        if json.loads(archivo.read_text(encoding="utf-8")).get("equipo") == nombre_equipo():
            archivo.unlink()
    except (OSError, ValueError):
        pass
    _ultimo_latido.pop(str(carpeta), None)


def copias_en_conflicto(carpeta: Path) -> list[str]:
    """Copias que crean OneDrive/Drive cuando dos equipos guardan a la vez.

    Ej.: 'gastos-DESKTOP-ABC.db', 'gastos (1).db', 'gastos (conflicted copy).db'."""
    try:
        return sorted(
            a.name for a in carpeta.glob("gastos*.db")
            if a.name != NOMBRE_DB and ".respaldo-" not in a.name
        )
    except OSError:
        return []
