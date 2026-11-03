"""Notas del Resumen, con monto apartado opcional."""
from gestor.db import conectar


def contar(app):
    conn = conectar(app.config["DATABASE"])
    total = conn.execute("SELECT COUNT(*) FROM notas").fetchone()[0]
    conn.close()
    return total


def test_nota_con_monto_apartado(client):
    client.post("/movimientos/", data={"tipo": "ingreso", "fecha": "2026-10-01",
                                       "categoria": "Sueldo", "monto": "252467"})
    client.post("/notas", data={"texto": "Dejar guardado lo que me devolvieron del trabajo",
                                "monto": "47.900"})
    html = client.get("/").get_data(as_text=True)
    assert "Dejar guardado lo que me devolvieron del trabajo" in html
    assert "Apartado en notas" in html and "$47.900" in html
    assert "$204.567" in html                                  # libre: 252.467 − 47.900


def test_nota_sin_monto_y_marcar_hecha(app, client):
    client.post("/notas", data={"texto": "Pagar la luz"})
    html = client.get("/").get_data(as_text=True)
    assert "Pagar la luz" in html and "Apartado en notas" not in html

    client.post("/notas", data={"texto": "Reserva", "monto": "10000"})
    client.post("/notas/2/hecha")                              # una nota hecha ya no aparta dinero
    html = client.get("/").get_data(as_text=True)
    assert "nota-item--hecha" in html and "Apartado en notas" not in html
    client.post("/notas/2/hecha")                              # se puede desmarcar
    assert "Apartado en notas" in client.get("/").get_data(as_text=True)


def test_eliminar_nota_y_validaciones(app, client):
    client.post("/notas", data={"texto": "Algo", "monto": "5000"})
    client.post("/notas/1/eliminar")
    assert contar(app) == 0

    r = client.post("/notas", data={"texto": "   "}, follow_redirects=True)
    assert "obligatorio" in r.get_data(as_text=True)
    r = client.post("/notas", data={"texto": "Algo", "monto": "abc"}, follow_redirects=True)
    assert "número entero" in r.get_data(as_text=True)
    assert contar(app) == 0


def test_las_notas_se_ven_en_cualquier_mes_y_vuelve_al_mismo_mes(client):
    client.post("/notas", data={"texto": "Recordatorio"})
    assert "Recordatorio" in client.get("/?mes=2026-02").get_data(as_text=True)
    r = client.post("/notas", data={"texto": "Otra", "mes": "2026-09"})
    assert "mes=2026-09" in r.headers["Location"] and r.headers["Location"].endswith("#notas")
