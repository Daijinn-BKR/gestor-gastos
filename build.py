"""Genera el ejecutable con PyInstaller.

    pip install -r requirements-dev.txt
    python build.py

El resultado queda en dist/ (GestorGastos.exe en Windows).
El ejecutable se genera para el sistema donde corres este script:
en Windows sale un .exe, en macOS una app de Mac.
"""
import os

import PyInstaller.__main__

SEP = os.pathsep  # ';' en Windows, ':' en macOS/Linux

PyInstaller.__main__.run([
    "main.py",
    "--name=GestorGastos",
    "--onefile",          # un solo archivo
    "--windowed",         # sin ventana de consola
    "--noconfirm",
    "--clean",
    f"--add-data=gestor/templates{SEP}gestor/templates",
    f"--add-data=gestor/static{SEP}gestor/static",
    f"--add-data=gestor/schema.sql{SEP}gestor",
])
