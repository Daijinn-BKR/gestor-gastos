"""Sección 1: ingresos y egresos de la cuenta principal."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from ..db import get_db
from ..utils import (CATEGORIAS, ErrorValidacion, mes_valido, mover_mes,
                     parse_fecha, parse_monto, parse_texto)

bp = Blueprint("movimientos", __name__, url_prefix="/movimientos")


def saldo_cuenta(conn, hasta: str | None = None) -> int:
    """Saldo de la cuenta principal (opcionalmente, al cierre de la fecha `hasta`)."""
    fila = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto ELSE -monto END), 0) "
        "FROM movimientos WHERE fecha <= ?", (hasta or "9999-12-31",)
    ).fetchone()
    return fila[0]


def totales_mes(conn, mes: str) -> dict:
    fila = conn.execute(
        "SELECT "
        "COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto END), 0) AS ingresos, "
        "COALESCE(SUM(CASE WHEN tipo = 'egreso'  THEN monto END), 0) AS egresos "
        "FROM movimientos WHERE substr(fecha, 1, 7) = ?",
        (mes,),
    ).fetchone()
    return {"ingresos": fila["ingresos"], "egresos": fila["egresos"],
            "balance": fila["ingresos"] - fila["egresos"]}


# Columnas por las que se puede ordenar (lista blanca: nunca se arma SQL con texto del usuario)
ORDENES = {
    "fecha": "fecha {dir}, id {dir}",
    "categoria": "categoria COLLATE NOCASE {dir}, fecha DESC, id DESC",
    "monto": "monto {dir}, fecha DESC, id DESC",
}
ORDEN_POR_DEFECTO = {"col": "fecha", "dir": "desc"}


def orden_actual() -> dict:
    """Lee el orden de la URL (?orden=monto&dir=asc) o el último usado, y lo recuerda."""
    orden = dict(session.get("orden_movimientos", ORDEN_POR_DEFECTO))
    if request.args.get("orden") in ORDENES:
        orden["col"] = request.args["orden"]
    if request.args.get("dir") in ("asc", "desc"):
        orden["dir"] = request.args["dir"]
    session["orden_movimientos"] = orden
    return orden


@bp.get("/")
def lista():
    conn = get_db()
    mes = mes_valido(request.args.get("mes"))
    orden = orden_actual()
    filas = conn.execute(
        "SELECT * FROM movimientos WHERE substr(fecha, 1, 7) = ? ORDER BY "
        + ORDENES[orden["col"]].format(dir=orden["dir"].upper()),
        (mes,),
    ).fetchall()
    return render_template(
        "movimientos.html",
        movimientos=filas,
        mes=mes,
        mes_anterior=mover_mes(mes, -1),
        mes_siguiente=mover_mes(mes, 1),
        totales=totales_mes(conn, mes),
        saldo=saldo_cuenta(conn),
        categorias=CATEGORIAS,
        # Último tipo y fecha usados, para no tener que elegirlos de nuevo
        form=session.get("form_movimiento", {}),
        orden=orden,
    )


@bp.post("/")
def crear():
    tipo = request.form.get("tipo")
    try:
        if tipo not in ("ingreso", "egreso"):
            raise ErrorValidacion("Elige si es un ingreso o un egreso.")
        fecha = parse_fecha(request.form.get("fecha"))
        # Se recuerdan aunque falle otro campo, para no volver a elegirlos
        session["form_movimiento"] = {"tipo": tipo, "fecha": fecha}
        categoria = parse_texto(request.form.get("categoria"), "Categoría", largo=40)
        descripcion = parse_texto(request.form.get("descripcion"), "Descripción", obligatorio=False)
        monto = parse_monto(request.form.get("monto"))
    except ErrorValidacion as e:
        flash(str(e), "error")
        return redirect(url_for(".lista", mes=request.args.get("mes")))

    conn = get_db()
    conn.execute(
        "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) VALUES (?, ?, ?, ?, ?)",
        (fecha, tipo, categoria, descripcion, monto),
    )
    conn.commit()
    flash(f"{tipo.capitalize()} registrado.", "ok")
    return redirect(url_for(".lista", mes=fecha[:7]))


@bp.post("/<int:id>/eliminar")
def eliminar(id):
    conn = get_db()
    fila = conn.execute("SELECT fecha FROM movimientos WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM movimientos WHERE id = ?", (id,))
    conn.commit()
    flash("Movimiento eliminado.", "ok")
    return redirect(url_for(".lista", mes=fila["fecha"][:7] if fila else None))
