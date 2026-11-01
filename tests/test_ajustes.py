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


def test_color_de_acento(client):
    html = client.get("/").get_data(as_text=True)
    assert "--primario: #F2A5EA" in html                     # rosado por defecto

    client.post("/ajustes/color", data={"color": "#2f6fed"})
    html = client.get("/movimientos/").get_data(as_text=True)
    assert "--primario: #2F6FED" in html                     # se aplica en todas las páginas
    assert "Volver al color original" in client.get("/ajustes/").get_data(as_text=True)

    client.post("/ajustes/color/restablecer")
    assert "--primario: #F2A5EA" in client.get("/").get_data(as_text=True)


def test_color_invalido_no_se_guarda(client):
    r = client.post("/ajustes/color", data={"color": "red;}</style><script>alert(1)</script>"},
                    follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Color no válido" in html
    assert "<script>alert(1)" not in html
    assert "--primario: #F2A5EA" in html


def test_paleta_siempre_legible():
    from gestor.colores import FONDO_CLARO, SUPERFICIE_OSCURA, contraste, paleta
    for color in ["#F2A5EA", "#FFFF00", "#FFFFFF", "#000000", "#2F6FED", "#00FF00", "#777777"]:
        p = paleta(color)
        assert contraste(p["texto_claro"], FONDO_CLARO) >= 4.5, color
        assert contraste(p["texto_oscuro"], SUPERFICIE_OSCURA) >= 4.5, color
        assert contraste(p["primario"], p["sobre_primario"]) >= 3, color


def test_graficos_no_repiten_el_color_elegido():
    from gestor.colores import PREDEFINIDOS, series
    for color, _ in PREDEFINIDOS:
        otros = [claro for claro, _ in series(color)]
        assert len(otros) == 5 and color not in otros
    assert "#1F9D55" not in [c for c, _ in series("#1F9D55")]   # verde elegido → sin verde en el resto


def test_titulo_de_ajustes(client):
    html = client.get("/ajustes/").get_data(as_text=True)
    assert "<title>Ajustes · Gestor de gastos</title>" in html
    assert html.count('id="datos"') == 1
