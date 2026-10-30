"""Fondo de pantalla: se guarda en la carpeta de datos, nunca en el proyecto."""
from io import BytesIO
from pathlib import Path

from gestor import BASE_DIR

PNG_MINIMO = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
              b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
              b"\x00\x00\x00IEND\xaeB`\x82")


def subir(client, datos, nombre="fondo.png"):
    return client.post("/ajustes/fondo", data={"imagen": (BytesIO(datos), nombre)},
                       content_type="multipart/form-data", follow_redirects=True)


def test_sin_fondo_por_defecto(client):
    assert "fondo-app" not in client.get("/").get_data(as_text=True)
    assert client.get("/ajustes/fondo").status_code == 404


def test_subir_difuminar_y_quitar_fondo(app, client):
    r = subir(client, PNG_MINIMO)
    assert "Fondo de pantalla actualizado" in r.get_data(as_text=True)

    carpeta = Path(app.config["DATABASE"]).parent
    assert (carpeta / "fondo.png").exists()
    assert not list(BASE_DIR.glob("fondo.*"))           # nunca dentro del proyecto

    html = client.get("/").get_data(as_text=True)
    assert 'class="con-fondo"' in html and "blur(6px)" in html
    assert client.get("/ajustes/fondo").data == PNG_MINIMO

    client.post("/ajustes/fondo/difuminado", data={"difuminado": "12"})
    assert "blur(12px)" in client.get("/").get_data(as_text=True)
    client.post("/ajustes/fondo/difuminado", data={"difuminado": "999"})
    assert "blur(30px)" in client.get("/").get_data(as_text=True)   # se limita a 30

    client.post("/ajustes/fondo/quitar")
    assert not (carpeta / "fondo.png").exists()
    assert "fondo-app" not in client.get("/").get_data(as_text=True)


def test_rechaza_archivos_que_no_son_imagen(app, client):
    r = subir(client, b"MZ\x90\x00 esto es un programa", "foto.png")
    assert "no es una imagen válida" in r.get_data(as_text=True)
    assert not list(Path(app.config["DATABASE"]).parent.glob("fondo.*"))
