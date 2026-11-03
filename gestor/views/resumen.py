"""Página de inicio: resumen de las tres secciones y exportación a Excel."""
import calendar
from datetime import date
from io import BytesIO

from flask import (Blueprint, flash, redirect, render_template, request,
                   send_file, url_for)

from ..db import get_db
from ..exportar import generar_excel, nombre_archivo
from .ahorro import estado_ahorro
from .credito import resumen_general
from ..utils import (ErrorValidacion, mes_valido, mover_mes, parse_monto,
                     parse_texto)
from .movimientos import saldo_cuenta, totales_mes

bp = Blueprint("resumen", __name__)

MES_MINIMO = "2026-01"   # primer mes al que se puede retroceder


def _mes_pedido() -> str:
    """Mes de la URL (?mes=AAAA-MM), limitado entre enero 2026 y el mes actual."""
    actual = date.today().strftime("%Y-%m")
    mes = mes_valido(request.args.get("mes"))
    return min(max(mes, MES_MINIMO), actual)


@bp.get("/")
def inicio():
    conn = get_db()
    hoy = date.today()
    mes = _mes_pedido()
    es_actual = mes == hoy.strftime("%Y-%m")
    anio, num = map(int, mes.split("-"))
    cierre = date(anio, num, calendar.monthrange(anio, num)[1])
    # Mes actual: todo lo registrado. Meses pasados: saldos al último día de ese mes.
    hasta = None if es_actual else cierre.isoformat()

    por_categoria = conn.execute(
        "SELECT categoria, SUM(monto) AS total FROM movimientos "
        "WHERE tipo = 'egreso' AND substr(fecha, 1, 7) = ? "
        "GROUP BY categoria ORDER BY total DESC",
        (mes,),
    ).fetchall()
    maximo = por_categoria[0]["total"] if por_categoria else 0

    ultimos = conn.execute(
        "SELECT * FROM movimientos WHERE substr(fecha, 1, 7) = ? ORDER BY fecha DESC, id DESC LIMIT 6",
        (mes,),
    ).fetchall()

    notas = conn.execute("SELECT * FROM notas ORDER BY hecha, id DESC").fetchall()
    apartado = sum(n["monto"] or 0 for n in notas if not n["hecha"])
    saldo_actual = saldo_cuenta(conn)

    anterior, siguiente = mover_mes(mes, -1), mover_mes(mes, 1)
    return render_template(
        "resumen.html",
        mes=mes,
        es_actual=es_actual,
        mes_anterior=anterior if anterior >= MES_MINIMO else None,
        mes_siguiente=None if es_actual else siguiente,
        saldo=saldo_cuenta(conn, hasta),
        totales=totales_mes(conn, mes),
        credito=resumen_general(conn, hoy if es_actual else cierre, hasta),
        ahorro=estado_ahorro(conn, hasta),
        por_categoria=por_categoria,
        maximo=maximo,
        ultimos=ultimos,
        notas=notas,
        apartado=apartado,
        libre=saldo_actual - apartado,
    )


# ── Notas ────────────────────────────────────────────────────────────────

def _volver_al_resumen():
    mes = request.form.get("mes")
    return redirect(url_for(".inicio", mes=mes_valido(mes) if mes else None) + "#notas")


@bp.post("/notas")
def crear_nota():
    try:
        texto = parse_texto(request.form.get("texto"), "Nota", largo=300)
        texto_monto = (request.form.get("monto") or "").strip()
        monto = parse_monto(texto_monto) if texto_monto else None
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver_al_resumen()
    conn = get_db()
    conn.execute("INSERT INTO notas (creada, texto, monto) VALUES (?, ?, ?)",
                 (date.today().isoformat(), texto, monto))
    conn.commit()
    return _volver_al_resumen()


@bp.post("/notas/<int:id>/hecha")
def marcar_nota(id):
    conn = get_db()
    conn.execute("UPDATE notas SET hecha = 1 - hecha WHERE id = ?", (id,))
    conn.commit()
    return _volver_al_resumen()


@bp.post("/notas/<int:id>/eliminar")
def eliminar_nota(id):
    conn = get_db()
    conn.execute("DELETE FROM notas WHERE id = ?", (id,))
    conn.commit()
    return _volver_al_resumen()


@bp.get("/exportar")
def exportar():
    """Excel del mes que se está viendo (?mes=AAAA-MM). Descarga directa en modo navegador;
    en la app de escritorio se usa main.Api.exportar_excel con el mismo mes."""
    mes = _mes_pedido()
    return send_file(
        BytesIO(generar_excel(get_db(), mes)),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nombre_archivo(mes),
    )
