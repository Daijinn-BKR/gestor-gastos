"""Abre el Gestor de gastos como programa de escritorio, en su propia ventana.

Uso:
    python main.py           # tus datos reales
    python main.py --demo    # base aparte con datos ficticios
"""
import argparse
import os
import sys
from pathlib import Path


class Api:
    """Funciones de Python que la página puede llamar con window.pywebview.api.

    Los atributos empiezan con _ para que pywebview no los exponga a la página."""

    def __init__(self, app):
        self._app = app
        self._ventana = None

    def _guardar_como(self, nombre: str, tipo: str, extension: str, generar):
        """Abre el diálogo "Guardar como" y escribe lo que devuelve generar(conn, app)."""
        import webview

        from gestor.db import get_db

        try:
            # pywebview 6 usa FileDialog.SAVE; versiones anteriores, SAVE_DIALOG
            dialogo = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
            ruta = self._ventana.create_file_dialog(
                dialogo, save_filename=nombre, file_types=(f"{tipo} (*{extension})",)
            )
            if not ruta:
                return {"ok": False, "cancelado": True}
            if isinstance(ruta, (list, tuple)):
                ruta = ruta[0]
            ruta = Path(ruta)
            if ruta.suffix.lower() != extension:
                ruta = ruta.with_name(ruta.name + extension)
            with self._app.app_context():
                ruta.write_bytes(generar(get_db(), self._app))
            return {"ok": True, "ruta": str(ruta)}
        except PermissionError:
            return {"ok": False, "error": "el archivo está abierto en otro programa o no hay permiso para guardarlo."}
        except Exception as e:  # se muestra en la ventana en vez de fallar en silencio
            return {"ok": False, "error": str(e)}

    def elegir_carpeta(self):
        """Selector de carpetas de Windows (para la carpeta de datos sincronizada)."""
        import webview

        try:
            dialogo = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
            ruta = self._ventana.create_file_dialog(dialogo)
            if not ruta:
                return {"ruta": None}
            return {"ruta": str(ruta[0] if isinstance(ruta, (list, tuple)) else ruta)}
        except Exception as e:
            return {"ruta": None, "error": str(e)}

    def exportar_excel(self):
        from gestor.exportar import generar_excel, nombre_archivo

        return self._guardar_como(nombre_archivo(), "Archivos de Excel", ".xlsx",
                                  lambda conn, app: generar_excel(conn))

    def exportar_respaldo(self):
        from gestor.respaldo import generar_respaldo, nombre_archivo

        return self._guardar_como(nombre_archivo(), "Respaldo del Gestor de gastos", ".zip",
                                  lambda conn, app: generar_respaldo(conn, Path(app.config["DATABASE"]).parent))


def preparar_demo():
    """Usa una base separada (demo.db) y la llena con datos ficticios si está vacía."""
    os.environ["GESTOR_DB"] = "demo.db"
    from gestor import create_app
    from gestor.db import get_db
    from gestor.seed import cargar_datos_demo

    app = create_app()
    with app.app_context():
        conn = get_db()
        if conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0:
            cargar_datos_demo(conn)
    return app


def main():
    parser = argparse.ArgumentParser(description="Gestor de gastos")
    parser.add_argument("--demo", action="store_true", help="abrir con datos ficticios")
    args = parser.parse_args()

    import webview

    from gestor import create_app

    app = preparar_demo() if args.demo else create_app()
    titulo = "Gestor de gastos" + (" (demo)" if args.demo else "")

    # pywebview sirve la app Flask internamente y la muestra en una ventana nativa
    # (Edge WebView2 en Windows, WebKit en macOS, GTK/Qt en Linux). No abre el navegador.
    api = Api(app)
    api._ventana = webview.create_window(titulo, app, js_api=api,
                                         width=1200, height=860, min_size=(820, 600))
    webview.start()

    # Al cerrar la ventana: quitar la marca de "app abierta en este computador"
    from gestor import ubicacion
    ubicacion.liberar(Path(app.config["DATABASE"]).parent)


if __name__ == "__main__":
    sys.exit(main())
