"""Carpeta de datos configurable: dos computadores que comparten una carpeta de OneDrive."""
import json
import time
from pathlib import Path

import pytest

from gestor import create_app, ubicacion


def computador(tmp_path, nombre):
    """Una 'instalación' con su propia carpeta por defecto y su propio ubicacion.json."""
    local = tmp_path / nombre
    local.mkdir()
    config = {"TESTING": True, "CARPETA_POR_DEFECTO": str(local),
              "ARCHIVO_UBICACION": str(local / "ubicacion.json")}
    app = create_app(config)
    return app, app.test_client(), config


def nuevo_inicio(config):
    """Simula cerrar y volver a abrir la app con la misma configuración."""
    app = create_app(dict(config))
    return app, app.test_client()


@pytest.fixture
def onedrive(tmp_path):
    carpeta = tmp_path / "OneDrive" / "GestorGastos"
    carpeta.mkdir(parents=True)
    return carpeta


def test_mover_datos_a_onedrive_y_usarlos_en_otro_pc(tmp_path, onedrive):
    # PC 1: tiene datos y los mueve a OneDrive
    app1, pc1, conf1 = computador(tmp_path, "pc1")
    pc1.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                    "categoria": "Sueldo", "monto": "950000"})
    html = pc1.post("/ajustes/carpeta", data={"carpeta": str(onedrive)},
                    follow_redirects=True).get_data(as_text=True)
    assert "se copiaron a la nueva carpeta" in html
    assert (onedrive / "gastos.db").exists()
    assert (tmp_path / "pc1" / "gastos.db").exists()              # la copia original sigue ahí

    # Al volver a abrir, PC 1 recuerda la carpeta
    app1, pc1 = nuevo_inicio(conf1)
    assert app1.config["DATABASE"] == str(onedrive / "gastos.db")

    # PC 2: elige la misma carpeta → se le pregunta qué hacer → "Usar los datos de esa carpeta"
    app2, pc2, conf2 = computador(tmp_path, "pc2")
    html = pc2.post("/ajustes/carpeta", data={"carpeta": str(onedrive)},
                    follow_redirects=True).get_data(as_text=True)
    assert "ya tiene datos del Gestor de gastos" in html
    pc2.post("/ajustes/carpeta", data={"carpeta": str(onedrive), "accion": "usar"})
    assert "$950.000" in pc2.get("/movimientos/?mes=2026-10").get_data(as_text=True)

    # Lo que se anota en PC 2 lo ve PC 1
    pc2.post("/movimientos/", data={"tipo": "egreso", "fecha": "2026-10-02",
                                    "categoria": "Salud", "monto": "12345"})
    app1, pc1 = nuevo_inicio(conf1)
    assert "$12.345" in pc1.get("/movimientos/?mes=2026-10").get_data(as_text=True)


def test_reemplazar_guarda_copia_de_lo_que_habia(tmp_path, onedrive):
    _, pc1, _ = computador(tmp_path, "pc1")
    pc1.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                    "categoria": "Sueldo", "monto": "111111"})
    pc1.post("/ajustes/carpeta", data={"carpeta": str(onedrive)})

    _, pc2, _ = computador(tmp_path, "pc2")
    pc2.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                    "categoria": "Sueldo", "monto": "222222"})
    pc2.post("/ajustes/carpeta", data={"carpeta": str(onedrive), "accion": "reemplazar"})
    html = pc2.get("/movimientos/?mes=2026-10").get_data(as_text=True)
    assert "$222.222" in html and "$111.111" not in html
    assert list(onedrive.glob("gastos.respaldo-*.db"))             # lo de PC 1 quedó respaldado


def test_volver_a_la_carpeta_local(tmp_path, onedrive):
    _, pc1, conf1 = computador(tmp_path, "pc1")
    pc1.post("/ajustes/carpeta", data={"carpeta": str(onedrive)})
    pc1.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                    "categoria": "Sueldo", "monto": "333333"})
    # La carpeta local ya tiene gastos.db (el original) → elegir "reemplazar" trae los datos de vuelta
    pc1.post("/ajustes/carpeta", data={"carpeta": conf1["CARPETA_POR_DEFECTO"], "accion": "reemplazar"})
    assert not Path(conf1["ARCHIVO_UBICACION"]).exists()           # vuelve al comportamiento normal
    app1, pc1 = nuevo_inicio(conf1)
    assert app1.config["DATABASE"] == str(Path(conf1["CARPETA_POR_DEFECTO"]) / "gastos.db")
    assert "$333.333" in pc1.get("/movimientos/?mes=2026-10").get_data(as_text=True)


def test_carpeta_no_disponible_avisa_y_no_crea_datos_vacios_alli(tmp_path, onedrive):
    _, pc1, conf1 = computador(tmp_path, "pc1")
    pc1.post("/ajustes/carpeta", data={"carpeta": str(onedrive)})
    onedrive.rename(tmp_path / "carpeta-desconectada")             # OneDrive "desconectado"
    app1, pc1 = nuevo_inicio(conf1)
    html = pc1.get("/").get_data(as_text=True)
    assert "No se encontró tu carpeta de datos" in html
    assert not onedrive.exists()


def test_validaciones(tmp_path):
    _, pc1, _ = computador(tmp_path, "pc1")
    for carpeta, mensaje in [("", "Escribe o elige"), ("relativa/carpeta", "ruta completa"),
                             (str(tmp_path / "no-existe"), "no existe")]:
        html = pc1.post("/ajustes/carpeta", data={"carpeta": carpeta},
                        follow_redirects=True).get_data(as_text=True)
        assert mensaje in html


def test_aviso_si_esta_abierta_en_otro_computador(tmp_path, onedrive):
    _, pc1, _ = computador(tmp_path, "pc1")
    pc1.post("/ajustes/carpeta", data={"carpeta": str(onedrive)})
    (onedrive / "en_uso.json").write_text(json.dumps({"equipo": "NOTEBOOK-TRABAJO", "hora": time.time()}))
    assert "abierta en <strong>NOTEBOOK-TRABAJO</strong>" in pc1.get("/").get_data(as_text=True)

    # Si el otro equipo no da señales hace rato, no se avisa
    (onedrive / "en_uso.json").write_text(json.dumps({"equipo": "NOTEBOOK-TRABAJO", "hora": time.time() - 3600}))
    assert "NOTEBOOK-TRABAJO" not in pc1.get("/").get_data(as_text=True)


def test_aviso_de_copias_en_conflicto(tmp_path, onedrive):
    _, pc1, _ = computador(tmp_path, "pc1")
    pc1.post("/ajustes/carpeta", data={"carpeta": str(onedrive)})
    (onedrive / "gastos-NOTEBOOK.db").write_bytes(b"")
    (onedrive / "gastos.respaldo-20261101-120000.db").write_bytes(b"")   # esto no es conflicto
    html = pc1.get("/").get_data(as_text=True)
    assert "copias en conflicto" in html and "gastos-NOTEBOOK.db" in html
    assert "respaldo-20261101" not in html.split("copias en conflicto")[1].split("</div>")[0]


def test_liberar_solo_borra_la_marca_propia(tmp_path):
    ubicacion.latido(tmp_path, forzar=True)
    assert (tmp_path / "en_uso.json").exists()
    ubicacion.liberar(tmp_path)
    assert not (tmp_path / "en_uso.json").exists()

    (tmp_path / "en_uso.json").write_text(json.dumps({"equipo": "OTRO", "hora": time.time()}))
    ubicacion.liberar(tmp_path)
    assert (tmp_path / "en_uso.json").exists()
