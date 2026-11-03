"""Sección 2: crédito. Varias cuentas (ej. Falabella, BCI), cada una con compras y pagos.

Cada cuenta puede tener además un cupo internacional en dólares. Los montos en dólares
se guardan en centavos y se llevan por separado: nunca se suman con pesos."""
from datetime import date

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from ..calculos import (calendario_cuotas, estado_cuotas, facturado_en,
                        periodo_facturacion, rango_periodo, resumen_credito,
                        sumar_meses)
from ..db import get_db
from ..utils import (CATEGORIAS, ErrorValidacion, parse_fecha, parse_monto,
                     parse_porcentaje, parse_texto, parse_usd, usd)

bp = Blueprint("credito", __name__, url_prefix="/credito")


# ── Consultas reutilizables (también las usa el Resumen y el Excel) ─────────

def listar_cuentas(conn):
    return conn.execute("SELECT * FROM credito_cuentas ORDER BY id").fetchall()


def resumen_cuenta(conn, cuenta, hoy: date | None = None, moneda: str = "CLP",
                   hasta: str | None = None):
    """Deuda, cupo disponible y próxima cuota de una cuenta, en pesos o en dólares (centavos).

    Con `hasta` (AAAA-MM-DD) solo cuenta compras y pagos hasta esa fecha: así el Resumen
    de un mes pasado muestra la deuda que había al cierre de ese mes."""
    hoy = hoy or date.today()
    filtro = "WHERE cuenta_id = ? AND moneda = ? AND fecha <= ?"
    args = (cuenta["id"], moneda, hasta or "9999-12-31")
    compras = conn.execute(f"SELECT * FROM credito_compras {filtro}", args).fetchall()
    pagos = conn.execute(f"SELECT * FROM credito_pagos {filtro}", args).fetchall()
    cupo = cuenta["cupo"] if moneda == "CLP" else cuenta["cupo_usd"]
    return resumen_credito(compras, pagos, cupo, hoy, cuenta["dia_facturacion"])


def usa_dolares(conn, cuenta) -> bool:
    """La cuenta tiene cupo internacional o ya tiene movimientos en dólares."""
    if cuenta["cupo_usd"]:
        return True
    return conn.execute(
        "SELECT 1 FROM credito_compras WHERE cuenta_id = ? AND moneda = 'USD' "
        "UNION SELECT 1 FROM credito_pagos WHERE cuenta_id = ? AND moneda = 'USD' LIMIT 1",
        (cuenta["id"], cuenta["id"]),
    ).fetchone() is not None


def resumen_general(conn, hoy: date | None = None, hasta: str | None = None) -> dict:
    """Totales de todas las cuentas de crédito (pesos y dólares por separado)."""
    detalle = []
    for c in listar_cuentas(conn):
        r_usd = resumen_cuenta(conn, c, hoy, "USD", hasta) if usa_dolares(conn, c) else None
        detalle.append((c, resumen_cuenta(conn, c, hoy, "CLP", hasta), r_usd))
    return {
        "cuentas": detalle,
        "deuda": sum(r.deuda for _, r, _ in detalle),
        "disponible": sum(r.disponible for _, r, _ in detalle),
        "proxima_cuota": sum(r.proxima_cuota for _, r, _ in detalle),
        # Dólares (en centavos), solo de las cuentas que usan dólares
        "usa_dolares": any(u for _, _, u in detalle),
        "deuda_usd": sum(u.deuda for _, _, u in detalle if u),
        "cupo_usd": sum(u.cupo for _, _, u in detalle if u),
        "disponible_usd": sum(u.disponible for _, _, u in detalle if u),
    }


def _cuenta_o_none(conn, cuenta_id):
    return conn.execute("SELECT * FROM credito_cuentas WHERE id = ?", (cuenta_id,)).fetchone()


def _volver(cuenta_id=None):
    return redirect(url_for(".lista", cuenta=cuenta_id))


def _recordar_fecha(fecha: str):
    session["fecha_credito"] = fecha


def _leer_moneda() -> str:
    moneda = request.form.get("moneda") or "CLP"
    if moneda not in ("CLP", "USD"):
        raise ErrorValidacion("Moneda no válida.")
    return moneda


# ── Página ───────────────────────────────────────────────────────────────

@bp.get("/")
def lista():
    conn = get_db()
    cuentas = listar_cuentas(conn)
    if not cuentas:
        return render_template("credito.html", cuentas=[], cuenta=None)

    cuenta = next((c for c in cuentas if str(c["id"]) == request.args.get("cuenta")), None)
    if cuenta is None:
        return panel(conn, cuentas)
    hoy = date.today()
    dia = cuenta["dia_facturacion"]
    compras = {"CLP": [], "USD": []}
    filas = conn.execute("SELECT * FROM credito_compras WHERE cuenta_id = ? "
                         "ORDER BY fecha DESC, id DESC", (cuenta["id"],)).fetchall()
    for c in filas:
        fecha = date.fromisoformat(c["fecha"])
        estado = estado_cuotas(c["monto"], c["cuotas"], fecha, hoy, c["interes"], dia)
        compras[c["moneda"]].append({**dict(c), "estado": estado, "periodo": periodo_facturacion(fecha, dia)})
    pagos = conn.execute("SELECT * FROM credito_pagos WHERE cuenta_id = ? ORDER BY fecha DESC, id DESC",
                         (cuenta["id"],)).fetchall()
    dolares = usa_dolares(conn, cuenta)

    return render_template(
        "credito.html",
        cuentas=cuentas,
        cuenta=cuenta,
        compras=compras,
        periodos={m: _agrupar_por_periodo(compras[m], dia) for m in compras},
        facturacion=_facturacion(filas, dia, hoy),
        pagos=pagos,
        resumen=resumen_cuenta(conn, cuenta, hoy),
        resumen_usd=resumen_cuenta(conn, cuenta, hoy, "USD") if dolares else None,
        categorias=CATEGORIAS,
        fecha_form=session.get("fecha_credito"),
    )


def _agrupar_por_periodo(compras, dia):
    """[(periodo, desde, hasta, compras, total)] del más reciente al más antiguo."""
    grupos = {}
    for c in compras:
        grupos.setdefault(c["periodo"], []).append(c)
    resultado = []
    for periodo in sorted(grupos, reverse=True):
        desde, hasta = rango_periodo(periodo, dia)
        resultado.append((periodo, desde, hasta, grupos[periodo], sum(c["monto"] for c in grupos[periodo])))
    return resultado


def _facturacion(compras, dia, hoy: date) -> dict:
    """Período abierto (el que se facturará en la próxima fecha) y el último estado de cuenta cerrado."""
    en_pesos = [c for c in compras if c["moneda"] == "CLP"]
    actual = periodo_facturacion(hoy, dia)
    anterior = sumar_meses(actual, -1)
    desde, hasta = rango_periodo(actual, dia)
    return {
        "dia": dia,
        "actual": actual,
        "desde": desde,
        "hasta": hasta,
        "dias_restantes": (hasta - hoy).days,
        "compras": sum(c["monto"] for c in en_pesos if periodo_facturacion(date.fromisoformat(c["fecha"]), dia) == actual),
        "a_facturar": facturado_en(en_pesos, actual, dia),
        "anterior": anterior,
        "cierre_anterior": rango_periodo(anterior, dia)[1],
        "facturado_anterior": facturado_en(en_pesos, anterior, dia),
    }


# ── Panel general de todos los créditos ─────────────────────────────────

def panel(conn, cuentas):
    hoy = date.today()
    general = resumen_general(conn, hoy)
    cupo_total = sum(c["cupo"] for c in cuentas)

    # Calendario de cuotas de los próximos 12 meses, separado por crédito
    calendario = {}
    for c in cuentas:
        compras = conn.execute("SELECT * FROM credito_compras WHERE cuenta_id = ? AND moneda = 'CLP'",
                               (c["id"],)).fetchall()
        calendario[c["id"]] = calendario_cuotas(compras, hoy, 12, c["dia_facturacion"])
    meses = list(next(iter(calendario.values())).keys())
    columnas = [
        {"mes": m, "total": sum(calendario[c["id"]][m] for c in cuentas),
         "partes": [(i, c, calendario[c["id"]][m]) for i, c in enumerate(cuentas) if calendario[c["id"]][m]]}
        for m in meses
    ]
    maximo = max((col["total"] for col in columnas), default=0)

    # Intereses de compras que todavía tienen cuotas por pagar
    intereses = 0
    dias = {c["id"]: c["dia_facturacion"] for c in cuentas}
    for c in conn.execute("SELECT * FROM credito_compras WHERE moneda = 'CLP' AND cuotas > 1 AND interes > 0"):
        e = estado_cuotas(c["monto"], c["cuotas"], date.fromisoformat(c["fecha"]), hoy, c["interes"],
                          dias.get(c["cuenta_id"]))
        if e.restantes:
            intereses += e.intereses

    # Compras con tarjeta de los últimos 6 meses, por categoría
    desde = sumar_meses(hoy.strftime("%Y-%m"), -5) + "-01"
    categorias = conn.execute(
        "SELECT categoria, SUM(monto) AS total, COUNT(*) AS cantidad FROM credito_compras "
        "WHERE moneda = 'CLP' AND fecha >= ? GROUP BY categoria ORDER BY total DESC",
        (desde,),
    ).fetchall()

    return render_template(
        "credito_panel.html",
        cuentas=cuentas,
        general=general,
        cupo_total=cupo_total,
        uso=round(general["deuda"] / cupo_total * 100, 1) if cupo_total else 0,
        columnas=columnas,
        maximo=maximo,
        intereses=intereses,
        categorias=categorias,
        maximo_categoria=categorias[0]["total"] if categorias else 0,
        desde=desde,
    )


# ── Cuentas ──────────────────────────────────────────────────────────────

def _leer_cuenta(conn, excluir_id=None):
    nombre = parse_texto(request.form.get("nombre"), "Nombre", largo=40)
    cupo = parse_monto(request.form.get("cupo"))
    texto_usd = (request.form.get("cupo_usd") or "").strip()
    cupo_usd = parse_usd(texto_usd, "Cupo internacional") if texto_usd not in ("", "0") else 0
    repetida = conn.execute(
        "SELECT 1 FROM credito_cuentas WHERE lower(nombre) = lower(?) AND id IS NOT ?",
        (nombre, excluir_id),
    ).fetchone()
    if repetida:
        raise ErrorValidacion(f"Ya tienes un crédito llamado «{nombre}».")
    texto_dia = (request.form.get("dia_facturacion") or "").strip()
    dia = None
    if texto_dia:
        try:
            dia = int(texto_dia)
        except ValueError:
            dia = 0
        if not 1 <= dia <= 31:
            raise ErrorValidacion("El día de facturación debe estar entre 1 y 31.")
    return nombre, cupo, cupo_usd, dia


@bp.post("/cuentas")
def crear_cuenta():
    conn = get_db()
    try:
        nombre, cupo, cupo_usd, dia = _leer_cuenta(conn)
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver(request.form.get("desde"))
    cur = conn.execute("INSERT INTO credito_cuentas (nombre, cupo, cupo_usd, dia_facturacion) VALUES (?, ?, ?, ?)",
                       (nombre, cupo, cupo_usd, dia))
    conn.commit()
    flash(f"Crédito «{nombre}» agregado.", "ok")
    return _volver(cur.lastrowid)


@bp.post("/cuentas/<int:id>/editar")
def editar_cuenta(id):
    conn = get_db()
    try:
        nombre, cupo, cupo_usd, dia = _leer_cuenta(conn, excluir_id=id)
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver(id)
    conn.execute("UPDATE credito_cuentas SET nombre = ?, cupo = ?, cupo_usd = ?, dia_facturacion = ? WHERE id = ?",
                 (nombre, cupo, cupo_usd, dia, id))
    conn.commit()
    flash("Crédito actualizado.", "ok")
    return _volver(id)


@bp.post("/cuentas/<int:id>/eliminar")
def eliminar_cuenta(id):
    conn = get_db()
    cuenta = _cuenta_o_none(conn, id)
    # Las compras y pagos de la cuenta se borran en cascada.
    # Los egresos que ya quedaron en Movimientos se mantienen: ese dinero sí salió.
    conn.execute("DELETE FROM credito_cuentas WHERE id = ?", (id,))
    conn.commit()
    if cuenta:
        flash(f"Crédito «{cuenta['nombre']}» eliminado.", "ok")
    return _volver()


# ── Compras y pagos ──────────────────────────────────────────────────────

@bp.post("/cuentas/<int:cuenta_id>/compras")
def crear_compra(cuenta_id):
    conn = get_db()
    if not _cuenta_o_none(conn, cuenta_id):
        return _volver()
    try:
        fecha = parse_fecha(request.form.get("fecha"))
        categoria = parse_texto(request.form.get("categoria"), "Categoría", largo=40)
        descripcion = parse_texto(request.form.get("descripcion"), "Descripción", obligatorio=False)
        moneda = _leer_moneda()
        monto = parse_usd(request.form.get("monto")) if moneda == "USD" else parse_monto(request.form.get("monto"))
        try:
            cuotas = int(request.form.get("cuotas") or 1)
        except ValueError:
            raise ErrorValidacion("Cuotas no válidas.") from None
        if not 1 <= cuotas <= 48:
            raise ErrorValidacion("Las cuotas deben estar entre 1 y 48.")
        interes = parse_porcentaje(request.form.get("interes"), "Interés mensual", maximo=20)
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver(cuenta_id)

    _recordar_fecha(fecha)
    cuenta = _cuenta_o_none(conn, cuenta_id)
    if monto > resumen_cuenta(conn, cuenta, moneda=moneda).disponible:
        cupo = "internacional" if moneda == "USD" else "disponible"
        flash(f"Ojo: esta compra supera el cupo {cupo} de este crédito.", "aviso")
    conn.execute(
        "INSERT INTO credito_compras (cuenta_id, fecha, categoria, descripcion, monto, cuotas, interes, moneda) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (cuenta_id, fecha, categoria, descripcion, monto, cuotas, interes if cuotas > 1 else 0, moneda),
    )
    conn.commit()
    flash("Compra registrada.", "ok")
    return _volver(cuenta_id)


@bp.post("/cuentas/<int:cuenta_id>/pagos")
def crear_pago(cuenta_id):
    conn = get_db()
    cuenta = _cuenta_o_none(conn, cuenta_id)
    if not cuenta:
        return _volver()
    try:
        fecha = parse_fecha(request.form.get("fecha"))
        descripcion = parse_texto(request.form.get("descripcion"), "Descripción", obligatorio=False)
        moneda = _leer_moneda()
        registrar_egreso = bool(request.form.get("registrar_egreso"))
        monto_clp = None
        if moneda == "USD":
            monto = parse_usd(request.form.get("monto"))
            texto_clp = (request.form.get("monto_clp") or "").strip()
            if texto_clp:
                monto_clp = parse_monto(texto_clp)
            elif registrar_egreso:
                raise ErrorValidacion("Para registrar el egreso, escribe cuántos pesos pagaste por esos dólares.")
        else:
            monto = parse_monto(request.form.get("monto"))
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver(cuenta_id)

    _recordar_fecha(fecha)
    deuda = resumen_cuenta(conn, cuenta, moneda=moneda).deuda
    if monto > deuda:
        texto = f"la deuda en dólares ({usd(deuda)})" if moneda == "USD" else "la deuda actual"
        flash(f"El pago es mayor que {texto} de este crédito.", "error")
        return _volver(cuenta_id)

    movimiento_id = None
    if registrar_egreso:
        detalle = f" ({usd(monto)})" if moneda == "USD" else ""
        cur = conn.execute(
            "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
            "VALUES (?, 'egreso', 'Tarjeta de crédito', ?, ?)",
            (fecha, (descripcion or f"Pago {cuenta['nombre']}") + detalle,
             monto_clp if moneda == "USD" else monto),
        )
        movimiento_id = cur.lastrowid
    conn.execute(
        "INSERT INTO credito_pagos (cuenta_id, fecha, descripcion, monto, movimiento_id, moneda, monto_clp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cuenta_id, fecha, descripcion, monto, movimiento_id, moneda, monto_clp),
    )
    conn.commit()
    flash("Pago registrado.", "ok")
    return _volver(cuenta_id)


@bp.post("/compras/<int:id>/eliminar")
def eliminar_compra(id):
    conn = get_db()
    fila = conn.execute("SELECT cuenta_id FROM credito_compras WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM credito_compras WHERE id = ?", (id,))
    conn.commit()
    flash("Compra eliminada.", "ok")
    return _volver(fila["cuenta_id"] if fila else None)


@bp.post("/pagos/<int:id>/eliminar")
def eliminar_pago(id):
    conn = get_db()
    fila = conn.execute("SELECT cuenta_id, movimiento_id FROM credito_pagos WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM credito_pagos WHERE id = ?", (id,))
    if fila and fila["movimiento_id"]:
        conn.execute("DELETE FROM movimientos WHERE id = ?", (fila["movimiento_id"],))
    conn.commit()
    flash("Pago eliminado.", "ok")
    return _volver(fila["cuenta_id"] if fila else None)
