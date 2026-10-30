"""Página de inicio: resumen de las tres secciones y exportación a Excel."""
from datetime import date
from io import BytesIO

from flask import Blueprint, render_template, send_file

from ..db import get_db
from ..exportar import generar_excel, nombre_archivo
from .ahorro import estado_ahorro
from .credito import resumen_general
from .movimientos import saldo_cuenta, totales_mes

bp = Blueprint("resumen", __name__)


@bp.get("/")
def inicio():
    conn = get_db()
    mes = date.today().strftime("%Y-%m")

    por_categoria = conn.execute(
        "SELECT categoria, SUM(monto) AS total FROM movimientos "
        "WHERE tipo = 'egreso' AND substr(fecha, 1, 7) = ? "
        "GROUP BY categoria ORDER BY total DESC",
        (mes,),
    ).fetchall()
    maximo = por_categoria[0]["total"] if por_categoria else 0

    ultimos = conn.execute(
        "SELECT * FROM movimientos ORDER BY fecha DESC, id DESC LIMIT 6"
    ).fetchall()

    return render_template(
        "resumen.html",
        mes=mes,
        saldo=saldo_cuenta(conn),
        totales=totales_mes(conn, mes),
        credito=resumen_general(conn),
        ahorro=estado_ahorro(conn),
        por_categoria=por_categoria,
        maximo=maximo,
        ultimos=ultimos,
    )


@bp.get("/exportar")
def exportar():
    """Descarga directa (modo navegador). En la app de escritorio se usa main.Api."""
    return send_file(
        BytesIO(generar_excel(get_db())),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nombre_archivo(),
    )
