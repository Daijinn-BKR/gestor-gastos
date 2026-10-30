"""Dónde se guardan los datos del usuario según el sistema operativo."""
import os
import sys
from pathlib import Path

NOMBRE_APP = "GestorGastos"


def carpeta_datos() -> Path:
    """Carpeta de datos del usuario, fuera de la carpeta del proyecto.

    Windows: %APPDATA%\\GestorGastos
    macOS:   ~/Library/Application Support/GestorGastos
    Linux:   ~/.local/share/GestorGastos
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / NOMBRE_APP
