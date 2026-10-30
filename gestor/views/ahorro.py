"""Sección 3: cuenta de ahorro (depósitos, retiros, meta y tasa de interés).

Los intereses pueden registrarse a mano o sumarse solos:
- "diario": cada día se calcula el interés y se va sumando a una fila por mes
  ("Intereses octubre 2026 (automático)").
- "mensual": se acumula día a día y se suma el último día de cada mes.
"""
import calendar
from datetime import date, timedelta

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from ..calculos import (interes_ahorro, progreso_meta, saldo_ahorro,
                        tasa_desde_pago, tasa_diaria)
from ..db import get_config, get_config_texto, get_db, set_config
from ..utils import (ErrorValidacion, clp, nombre_mes, parse_fecha,
                     parse_monto, parse_porcentaje, parse_texto, pct)

bp = Blueprint("ahorro", __name__, url_prefix="/ahorro")

MODOS = {
    "manual": "Yo los registro",
    "diario": "Automáticamente cada día",
    "mensual": "Automáticamente cada mes",
}
PERIODOS = {"dia": "al día", "mes": "al mes", "anio": "al año"}


# ── Estado ───────────────────────────────────────────────────────────────

def estado_ahorro(conn) -> dict:
    registros = conn.execute("SELECT tipo, monto FROM ahorro").fetchall()
    saldo = saldo_ahorro(registros)
    meta = get_config("meta_ahorro", 0)
    tasa = get_config("tasa_ahorro", 0)
    interes_mes, interes_anio = interes_ahorro(saldo, tasa)
    return {"saldo": saldo, "meta": meta, "progreso": progreso_meta(saldo, meta),
            "falta": max(0, meta - saldo), "tasa": tasa,
            "interes_dia": round(max(0, saldo) * tasa_diaria(tasa)) if tasa else 0,
            "interes_mes": interes_mes, "interes_anio": interes_anio,
            "modo": get_config_texto("interes_modo", "manual"),
            "pendiente": int(float(get_config_texto("interes_pendiente", "0") or 0))}


# ── Intereses automáticos ────────────────────────────────────────────────

def _descripcion_automatica(dia: date) -> str:
    return f"Intereses {nombre_mes(dia.strftime('%Y-%m'))} (automático)"


def _sumar_a_fila_del_mes(conn, dia: date, monto: int):
    """Suma el interés a la fila automática de ese mes (o la crea)."""
    texto = _descripcion_automatica(dia)
    fila = conn.execute("SELECT id FROM ahorro WHERE descripcion = ? AND tipo = 'deposito'", (texto,)).fetchone()
    if fila:
        conn.execute("UPDATE ahorro SET monto = monto + ?, fecha = ? WHERE id = ?",
                     (monto, dia.isoformat(), fila["id"]))
    else:
        conn.execute("INSERT INTO ahorro (fecha, tipo, descripcion, monto) VALUES (?, 'deposito', ?, ?)",
                     (dia.isoformat(), texto, monto))


def aplicar_intereses(conn, hoy: date | None = None) -> int:
    """Calcula los intereses de los días ya terminados desde la última vez. Devuelve lo sumado.

    Cada día se usa el saldo al cierre de ese día. Los centavos que sobran se guardan
    para el día siguiente, así no se pierde nada por redondeo."""
    hoy = hoy or date.today()
    modo = get_config_texto("interes_modo", "manual")
    if modo not in ("diario", "mensual"):
        return 0
    desde_texto = get_config_texto("interes_desde")
    if not desde_texto:
        set_config("interes_desde", hoy.isoformat())
        return 0
    dia = date.fromisoformat(desde_texto)
    tasa = get_config("tasa_ahorro", 0)
    if dia >= hoy:
        return 0
    if tasa <= 0:
        set_config("interes_desde", hoy.isoformat())
        return 0

    diaria = tasa_diaria(tasa)
    pendiente = float(get_config_texto("interes_pendiente", "0") or 0)
    registros = conn.execute("SELECT fecha, tipo, monto FROM ahorro ORDER BY fecha, id").fetchall()
    con_signo = [(r["fecha"], r["monto"] if r["tipo"] == "deposito" else -r["monto"]) for r in registros]
    saldo = sum(m for f, m in con_signo if f < dia.isoformat())
    i = sum(1 for f, _ in con_signo if f < dia.isoformat())
    sumado = 0

    while dia < hoy:  # solo días que ya terminaron
        while i < len(con_signo) and con_signo[i][0] <= dia.isoformat():
            saldo += con_signo[i][1]
            i += 1
        pendiente += max(0, saldo) * diaria
        ultimo_del_mes = dia.day == calendar.monthrange(dia.year, dia.month)[1]
        if modo == "diario" or (modo == "mensual" and ultimo_del_mes):
            entero = int(pendiente)
            if entero >= 1:
                _sumar_a_fila_del_mes(conn, dia, entero)
                pendiente -= entero
                saldo += entero
                sumado += entero
        dia += timedelta(days=1)

    set_config("interes_desde", hoy.isoformat())
    set_config("interes_pendiente", round(pendiente, 6))
    conn.commit()
    return sumado


@bp.before_app_request
def _intereses_al_abrir():
    """Antes de mostrar cualquier página, pone al día los intereses automáticos."""
    if request.endpoint and request.endpoint != "static":
        aplicar_intereses(get_db())


# ── Página ───────────────────────────────────────────────────────────────

def _volver():
    return redirect(url_for(".lista"))


@bp.get("/")
def lista():
    conn = get_db()
    registros = conn.execute("SELECT * FROM ahorro ORDER BY fecha DESC, id DESC").fetchall()
    return render_template("ahorro.html", registros=registros, estado=estado_ahorro(conn),
                           modos=MODOS, periodos=PERIODOS, fecha_form=session.get("fecha_ahorro"))


def _registrar(conn, tipo, fecha, descripcion, monto, vincular):
    movimiento_id = None
    if vincular:
        # Un depósito sale de la cuenta principal; un retiro vuelve a ella.
        tipo_mov = "egreso" if tipo == "deposito" else "ingreso"
        texto = descripcion or ("Depósito a ahorro" if tipo == "deposito" else "Retiro de ahorro")
        cur = conn.execute(
            "INSERT INTO movimientos (fecha, tipo, categoria, descripcion, monto) "
            "VALUES (?, ?, 'Ahorro', ?, ?)",
            (fecha, tipo_mov, texto, monto),
        )
        movimiento_id = cur.lastrowid
    conn.execute(
        "INSERT INTO ahorro (fecha, tipo, descripcion, monto, movimiento_id) VALUES (?, ?, ?, ?, ?)",
        (fecha, tipo, descripcion, monto, movimiento_id),
    )
    conn.commit()


@bp.post("/")
def crear():
    try:
        tipo = request.form.get("tipo")
        if tipo not in ("deposito", "retiro"):
            raise ErrorValidacion("Elige si es un depósito o un retiro.")
        fecha = parse_fecha(request.form.get("fecha"))
        session["fecha_ahorro"] = fecha
        descripcion = parse_texto(request.form.get("descripcion"), "Descripción", obligatorio=False)
        monto = parse_monto(request.form.get("monto"))
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver()

    conn = get_db()
    if tipo == "retiro" and monto > estado_ahorro(conn)["saldo"]:
        flash("No puedes retirar más de lo que tienes ahorrado.", "error")
        return _volver()

    _registrar(conn, tipo, fecha, descripcion, monto, bool(request.form.get("vincular")))
    flash("Depósito registrado." if tipo == "deposito" else "Retiro registrado.", "ok")
    return _volver()


@bp.post("/intereses")
def registrar_intereses():
    """Modo manual: agrega el interés estimado del mes como depósito."""
    conn = get_db()
    monto = estado_ahorro(conn)["interes_mes"]
    if monto <= 0:
        flash("Define una tasa anual y ten saldo ahorrado para calcular intereses.", "error")
        return _volver()
    hoy = date.today().isoformat()
    ya_registrado = conn.execute(
        "SELECT 1 FROM ahorro WHERE descripcion = ? LIMIT 1", (f"Intereses {nombre_mes(hoy[:7])}",)
    ).fetchone()
    if ya_registrado:
        flash("Ya registraste los intereses de este mes.", "aviso")
        return _volver()
    _registrar(conn, "deposito", hoy, f"Intereses {nombre_mes(hoy[:7])}", monto, vincular=False)
    flash("Interés del mes registrado. Si tu banco pagó otro monto, elimínalo y anota el real.", "ok")
    return _volver()


@bp.post("/intereses/modo")
def cambiar_modo():
    modo = request.form.get("modo")
    if modo not in MODOS:
        flash("Opción no válida.", "error")
        return _volver()
    conn = get_db()
    anterior = get_config_texto("interes_modo", "manual")
    if modo == anterior:
        return _volver()

    aplicar_intereses(conn)  # cierra lo calculado con el modo anterior
    pendiente = float(get_config_texto("interes_pendiente", "0") or 0)
    if anterior == "mensual" and pendiente >= 1:
        # Lo acumulado en el mes no se pierde al cambiar de opción
        _sumar_a_fila_del_mes(conn, date.today() - timedelta(days=1), int(pendiente))
        pendiente -= int(pendiente)
    set_config("interes_pendiente", round(pendiente, 6))
    set_config("interes_desde", date.today().isoformat())
    set_config("interes_modo", modo)
    conn.commit()

    if modo == "manual":
        flash("Listo: los intereses ya no se suman solos.", "ok")
    elif not get_config("tasa_ahorro", 0):
        flash("Opción guardada. Falta definir la tasa anual para que se calculen los intereses.", "aviso")
    else:
        cuando = "cada día" if modo == "diario" else "el último día de cada mes"
        flash(f"Listo: los intereses se sumarán solos {cuando}, a partir de mañana.", "ok")
    return _volver()


@bp.post("/meta")
def actualizar_meta():
    try:
        set_config("meta_ahorro", parse_monto(request.form.get("meta")))
        flash("Meta actualizada.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return _volver()


@bp.post("/tasa")
def actualizar_tasa():
    try:
        tasa = parse_porcentaje(request.form.get("tasa"), "Tasa anual", maximo=50)
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver()
    aplicar_intereses(get_db())  # lo anterior se calcula con la tasa anterior
    set_config("tasa_ahorro", tasa)
    flash("Tasa anual actualizada." if tasa else "Tasa anual eliminada.", "ok")
    return _volver()


@bp.post("/tasa/calcular")
def calcular_tasa():
    """Calcula la tasa anual a partir de lo que paga el banco (ej. $15 al día)."""
    conn = get_db()
    periodo = request.form.get("periodo")
    try:
        if periodo not in PERIODOS:
            raise ErrorValidacion("Elige si te pagan al día, al mes o al año.")
        pago = parse_monto(request.form.get("pago"))
        saldo = estado_ahorro(conn)["saldo"]
        if saldo <= 0:
            raise ErrorValidacion("Primero registra tu saldo ahorrado: la tasa se calcula a partir de él.")
        tasa = tasa_desde_pago(pago, saldo, periodo)
        if tasa > 50:
            raise ErrorValidacion(f"Con {clp(pago)} {PERIODOS[periodo]} sobre {clp(saldo)} la tasa sería "
                                  f"{pct(tasa)} anual, que no parece real. Revisa el monto o tu saldo.")
    except ErrorValidacion as e:
        flash(str(e), "error")
        return _volver()

    aplicar_intereses(conn)
    set_config("tasa_ahorro", tasa)
    flash(f"Con {clp(pago)} {PERIODOS[periodo]} sobre tu saldo de {clp(saldo)}, "
          f"tu tasa anual es {pct(tasa)}. Quedó guardada.", "ok")
    return _volver()


@bp.post("/<int:id>/eliminar")
def eliminar(id):
    conn = get_db()
    fila = conn.execute("SELECT movimiento_id FROM ahorro WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM ahorro WHERE id = ?", (id,))
    if fila and fila["movimiento_id"]:
        conn.execute("DELETE FROM movimientos WHERE id = ?", (fila["movimiento_id"],))
    conn.commit()
    flash("Registro eliminado.", "ok")
    return _volver()
