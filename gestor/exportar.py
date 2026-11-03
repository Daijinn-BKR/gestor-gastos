"""Exporta a Excel (.xlsx) el resumen y los registros de un mes."""
import calendar
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .calculos import estado_cuotas
from .utils import nombre_mes

PESOS = '"$"#,##0;[Red]-"$"#,##0'
DOLARES = '"US$" #,##0.00;[Red]-"US$" #,##0.00'
PORCENTAJE = '0.0#"%"'
FECHA = "DD-MM-YYYY"

ENCABEZADO = PatternFill("solid", fgColor="2F6FED")
SECCION = PatternFill("solid", fgColor="E8EEFB")


def _hoja(libro, titulo, columnas, filas, formatos=None, anchos=None):
    """Crea una hoja con encabezado, filtros y paneles congelados."""
    hoja = libro.create_sheet(titulo)
    hoja.append(columnas)
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = ENCABEZADO
        celda.alignment = Alignment(vertical="center")
    for fila in filas:
        hoja.append(fila)
    for col, formato in (formatos or {}).items():
        for (celda,) in hoja.iter_rows(min_row=2, min_col=col, max_col=col):
            celda.number_format = formato
    for i, ancho in enumerate(anchos or [], start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    hoja.freeze_panes = "A2"
    if filas:
        hoja.auto_filter.ref = hoja.dimensions
    return hoja


def _formato_moneda(hoja, monedas, columnas):
    """Aplica formato $ o US$ fila por fila según la moneda de cada registro."""
    for fila, moneda in enumerate(monedas, start=2):
        for col in columnas:
            hoja.cell(fila, col).number_format = DOLARES if moneda == "USD" else PESOS


def _fecha(texto):
    return date.fromisoformat(texto)


def generar_excel(conn, mes: str | None = None, hoy: date | None = None) -> bytes:
    """Excel del mes 'AAAA-MM' (por defecto, el actual), igual a lo que muestra el Resumen.

    Los saldos, la deuda y el ahorro son los del cierre del mes (o los de hoy si es el mes
    actual). Las hojas de detalle traen solo los registros de ese mes."""
    # Importes diferidos para evitar importaciones circulares
    from .views.ahorro import estado_ahorro
    from .views.credito import listar_cuentas, resumen_general
    from .views.movimientos import saldo_cuenta, totales_mes

    hoy = hoy or date.today()
    mes = mes or hoy.strftime("%Y-%m")
    es_actual = mes == hoy.strftime("%Y-%m")
    anio, num = map(int, mes.split("-"))
    cierre = hoy if es_actual else date(anio, num, calendar.monthrange(anio, num)[1])
    hasta = None if es_actual else cierre.isoformat()

    libro = Workbook()
    libro.remove(libro.active)

    # ── Resumen ──────────────────────────────────────────────────────────
    totales = totales_mes(conn, mes)
    credito = resumen_general(conn, cierre, hasta)
    ahorro = estado_ahorro(conn, hasta)

    hoja = libro.create_sheet("Resumen")
    hoja["A1"] = f"Gestor de gastos · {nombre_mes(mes)}"
    hoja["A1"].font = Font(bold=True, size=16)
    hoja["A2"] = (f"Exportado el {hoy:%d-%m-%Y}" if es_actual
                  else f"Saldos al cierre del {cierre:%d-%m-%Y} · exportado el {hoy:%d-%m-%Y}")
    hoja["A2"].font = Font(italic=True, color="6B7385")

    def seccion(titulo):
        hoja.append([])
        hoja.append([titulo])
        fila = hoja.max_row
        for col in (1, 2):
            hoja.cell(fila, col).fill = SECCION
        hoja.cell(fila, 1).font = Font(bold=True)

    def dato(etiqueta, valor, formato=PESOS):
        hoja.append([etiqueta, valor])
        hoja.cell(hoja.max_row, 2).number_format = formato

    seccion(f"Cuenta principal · {nombre_mes(mes)}")
    dato("Saldo en cuenta", saldo_cuenta(conn, hasta))
    dato("Ingresos del mes", totales["ingresos"])
    dato("Egresos del mes", totales["egresos"])
    dato("Balance del mes", totales["balance"])

    seccion("Crédito")
    for cuenta, r, r_usd in credito["cuentas"]:
        dato(f"{cuenta['nombre']} · deuda", r.deuda)
        dato(f"{cuenta['nombre']} · cupo disponible", r.disponible)
        dato(f"{cuenta['nombre']} · próxima cuota", r.proxima_cuota)
        if r_usd:
            dato(f"{cuenta['nombre']} · deuda internacional", r_usd.deuda / 100, DOLARES)
            dato(f"{cuenta['nombre']} · cupo internacional disponible", r_usd.disponible / 100, DOLARES)
    dato("Deuda total en pesos", credito["deuda"])
    if credito["deuda_usd"]:
        dato("Deuda total en dólares", credito["deuda_usd"] / 100, DOLARES)

    seccion("Ahorro")
    dato("Saldo ahorrado", ahorro["saldo"])
    dato("Meta", ahorro["meta"])
    dato("Tasa anual", ahorro["tasa"], PORCENTAJE)
    dato("Interés estimado al mes", ahorro["interes_mes"])

    categorias = conn.execute(
        "SELECT categoria, SUM(monto) AS total FROM movimientos "
        "WHERE tipo = 'egreso' AND substr(fecha, 1, 7) = ? GROUP BY categoria ORDER BY total DESC",
        (mes,),
    ).fetchall()
    if categorias:
        seccion(f"Egresos por categoría · {nombre_mes(mes)}")
        for c in categorias:
            dato(c["categoria"], c["total"])

    hoja.column_dimensions["A"].width = 38
    hoja.column_dimensions["B"].width = 18

    # ── Movimientos ──────────────────────────────────────────────────────
    filas = [
        (_fecha(m["fecha"]), m["tipo"].capitalize(), m["categoria"], m["descripcion"],
         m["monto"] if m["tipo"] == "ingreso" else -m["monto"])
        for m in conn.execute("SELECT * FROM movimientos WHERE substr(fecha, 1, 7) = ? "
                              "ORDER BY fecha, id", (mes,))
    ]
    _hoja(libro, "Movimientos", ["Fecha", "Tipo", "Categoría", "Descripción", "Monto"], filas,
          {1: FECHA, 5: PESOS}, [13, 10, 20, 34, 14])

    # ── Crédito ──────────────────────────────────────────────────────────
    nombres = {c["id"]: c["nombre"] for c in listar_cuentas(conn)}
    dias = {c["id"]: c["dia_facturacion"] for c in listar_cuentas(conn)}
    filas, monedas = [], []
    for c in conn.execute("SELECT * FROM credito_compras WHERE substr(fecha, 1, 7) = ? "
                          "ORDER BY cuenta_id, moneda, fecha, id", (mes,)):
        e = estado_cuotas(c["monto"], c["cuotas"], _fecha(c["fecha"]), cierre, c["interes"],
                          dias.get(c["cuenta_id"]))
        div = 100 if c["moneda"] == "USD" else 1  # dólares se guardan en centavos
        filas.append((nombres.get(c["cuenta_id"], ""), _fecha(c["fecha"]), c["moneda"], c["categoria"],
                      c["descripcion"], c["monto"] / div, c["cuotas"], c["interes"],
                      e.cuota / div, e.total / div, e.facturadas))
        monedas.append(c["moneda"])
    hoja = _hoja(libro, "Crédito - compras",
                 ["Crédito", "Fecha", "Moneda", "Categoría", "Descripción", "Monto", "Cuotas",
                  "Interés mensual", "Valor cuota", "Total a pagar", "Cuotas cobradas"],
                 filas, {2: FECHA, 8: PORCENTAJE}, [16, 13, 9, 18, 30, 14, 9, 15, 14, 15, 15])
    _formato_moneda(hoja, monedas, columnas=(6, 9, 10))

    filas, monedas = [], []
    for p in conn.execute("SELECT * FROM credito_pagos WHERE substr(fecha, 1, 7) = ? "
                          "ORDER BY cuenta_id, fecha, id", (mes,)):
        div = 100 if p["moneda"] == "USD" else 1
        filas.append((nombres.get(p["cuenta_id"], ""), _fecha(p["fecha"]), p["moneda"], p["descripcion"],
                      p["monto"] / div, p["monto_clp"]))
        monedas.append(p["moneda"])
    hoja = _hoja(libro, "Crédito - pagos", ["Crédito", "Fecha", "Moneda", "Descripción", "Monto", "Pagado en pesos"],
                 filas, {2: FECHA, 6: PESOS}, [16, 13, 9, 30, 14, 16])
    _formato_moneda(hoja, monedas, columnas=(5,))

    # ── Ahorro ───────────────────────────────────────────────────────────
    filas = [
        (_fecha(a["fecha"]), "Depósito" if a["tipo"] == "deposito" else "Retiro", a["descripcion"],
         a["monto"] if a["tipo"] == "deposito" else -a["monto"])
        for a in conn.execute("SELECT * FROM ahorro WHERE substr(fecha, 1, 7) = ? "
                              "ORDER BY fecha, id", (mes,))
    ]
    _hoja(libro, "Ahorro", ["Fecha", "Tipo", "Descripción", "Monto"], filas,
          {1: FECHA, 4: PESOS}, [13, 11, 30, 14])

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def nombre_archivo(mes: str | None = None) -> str:
    """'gastos-2026-10.xlsx'"""
    return f"gastos-{mes or date.today().strftime('%Y-%m')}.xlsx"
