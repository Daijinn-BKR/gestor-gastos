"""Exportar e importar todos los datos."""
import sqlite3
import zipfile
from io import BytesIO
from pathlib import Path

from gestor import create_app
from tests.test_ajustes import PNG_MINIMO, subir


def importar(client, datos, nombre="respaldo.zip"):
    return client.post("/ajustes/respaldo/importar", data={"archivo": (BytesIO(datos), nombre)},
                       content_type="multipart/form-data", follow_redirects=True)


def test_exportar_e_importar_en_otro_computador(app, client, tmp_path):
    # Datos en el "computador 1"
    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                       "categoria": "Sueldo", "monto": "950000"})
    client.post("/credito/cuentas", data={"nombre": "BCI", "cupo": "1000000", "cupo_usd": "100"})
    client.post("/ajustes/color", data={"color": "#1F9D55"})
    subir(client, PNG_MINIMO)

    r = client.get("/ajustes/respaldo")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    with zipfile.ZipFile(BytesIO(r.data)) as zf:
        assert {"gastos.db", "fondo.png", "info.json"} <= set(zf.namelist())

    # "Computador 2": base vacía en otra carpeta
    otra = create_app({"TESTING": True, "DATABASE": str(tmp_path / "pc2" / "gastos.db")})
    c2 = otra.test_client()
    html = importar(c2, r.data).get_data(as_text=True)
    assert "Datos importados" in html
    assert "$950.000" in c2.get("/").get_data(as_text=True)
    assert "BCI" in c2.get("/credito/").get_data(as_text=True)
    assert "--primario: #1F9D55" in html                          # también el color
    assert (tmp_path / "pc2" / "fondo.png").read_bytes() == PNG_MINIMO


def test_importar_guarda_copia_de_los_datos_actuales(app, client):
    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                       "categoria": "Sueldo", "monto": "111111"})
    respaldo = client.get("/ajustes/respaldo").data
    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-02",
                                       "categoria": "Sueldo", "monto": "222222"})

    html = importar(client, respaldo).get_data(as_text=True)
    assert "quedaron guardados en" in html and ".respaldo-" in html
    assert "$222.222" not in client.get("/movimientos/?mes=2026-10").get_data(as_text=True)

    copias = list(Path(app.config["DATABASE"]).parent.glob("*.respaldo-*.db"))
    assert copias
    conn = sqlite3.connect(copias[0])
    assert conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0] == 2   # lo de antes, intacto
    conn.close()


def test_rechaza_archivos_invalidos_sin_tocar_los_datos(app, client):
    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                       "categoria": "Sueldo", "monto": "500000"})
    for datos, mensaje in [
        (b"esto no es un respaldo", "no es un respaldo"),
        (_zip({"otra_cosa.txt": b"hola"}), "no contiene gastos.db"),
        (_zip({"gastos.db": b"SQLite format 3\x00" + b"\x00" * 200}), "dañado"),
        (_zip({"gastos.db": _base_ajena()}), "no es del Gestor de gastos"),
    ]:
        assert mensaje in importar(client, datos).get_data(as_text=True)
    assert "$500.000" in client.get("/movimientos/?mes=2026-10").get_data(as_text=True)
    assert not list(Path(app.config["DATABASE"]).parent.glob("*.respaldo-*.db"))


def test_acepta_un_db_suelto(app, client, tmp_path):
    client.post("/movimientos/", data={"tipo": "egreso", "fecha": "2026-10-03",
                                       "categoria": "Salud", "monto": "7000"})
    db = Path(app.config["DATABASE"]).read_bytes()
    otra = create_app({"TESTING": True, "DATABASE": str(tmp_path / "otro" / "gastos.db")})
    c2 = otra.test_client()
    assert "Datos importados" in importar(c2, db, "gastos.db").get_data(as_text=True)
    assert "$7.000" in c2.get("/movimientos/?mes=2026-10").get_data(as_text=True)


def _zip(archivos):
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w") as zf:
        for nombre, datos in archivos.items():
            zf.writestr(nombre, datos)
    return salida.getvalue()


def _base_ajena():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "x.db"
        conn = sqlite3.connect(ruta)
        conn.execute("CREATE TABLE clientes (id INTEGER)")
        conn.commit()
        conn.close()
        return ruta.read_bytes()
