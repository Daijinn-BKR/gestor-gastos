"""Cálculos puros (sin base de datos), fáciles de testear."""
from dataclasses import dataclass
from datetime import date


def _campo(fila, nombre, por_defecto=0):
    """Lee un campo de un dict o sqlite3.Row, con valor por defecto si no existe."""
    try:
        valor = fila[nombre]
    except (KeyError, IndexError):
        return por_defecto
    return por_defecto if valor is None else valor


def meses_entre(desde: date, hasta: date) -> int:
    """Cantidad de cambios de mes entre dos fechas (puede ser negativa)."""
    return (hasta.year - desde.year) * 12 + (hasta.month - desde.month)


# ── Crédito ──────────────────────────────────────────────────────────────

def valor_cuota(monto: int, cuotas: int, interes_mensual: float = 0) -> int:
    """Cuota fija (sistema francés). interes_mensual en %, ej. 2.1 para 2,1% mensual."""
    i = interes_mensual / 100
    if cuotas <= 1 or i <= 0:
        return round(monto / cuotas)
    return round(monto * i / (1 - (1 + i) ** -cuotas))


def total_a_pagar(monto: int, cuotas: int, interes_mensual: float = 0) -> int:
    if cuotas <= 1 or interes_mensual <= 0:
        return monto
    return valor_cuota(monto, cuotas, interes_mensual) * cuotas


@dataclass
class EstadoCuotas:
    cuota: int            # valor de cada cuota
    facturadas: int       # cuotas ya cobradas
    restantes: int        # cuotas que faltan
    total: int            # total a pagar, con intereses
    intereses: int        # total - monto


def estado_cuotas(monto: int, cuotas: int, fecha_compra: date, hoy: date,
                  interes_mensual: float = 0) -> EstadoCuotas:
    """La primera cuota se factura el mes siguiente a la compra."""
    facturadas = max(0, min(cuotas, meses_entre(fecha_compra, hoy)))
    total = total_a_pagar(monto, cuotas, interes_mensual)
    return EstadoCuotas(
        cuota=valor_cuota(monto, cuotas, interes_mensual),
        facturadas=facturadas,
        restantes=cuotas - facturadas,
        total=total,
        intereses=total - monto,
    )


@dataclass
class ResumenCredito:
    cupo: int
    deuda: int
    disponible: int
    proxima_cuota: int
    porcentaje_usado: float


def resumen_credito(compras, pagos, cupo: int, hoy: date) -> ResumenCredito:
    """compras: filas con monto, cuotas, fecha (e interes opcional) · pagos: filas con monto.

    La deuda incluye los intereses de las compras en cuotas."""
    total_compras = 0
    proxima = 0
    for c in compras:
        estado = estado_cuotas(c["monto"], c["cuotas"], date.fromisoformat(c["fecha"]), hoy,
                               _campo(c, "interes"))
        total_compras += estado.total
        if estado.restantes > 0:
            proxima += estado.cuota

    deuda = max(0, total_compras - sum(p["monto"] for p in pagos))
    return ResumenCredito(
        cupo=cupo,
        deuda=deuda,
        disponible=cupo - deuda,
        proxima_cuota=min(proxima, deuda),
        porcentaje_usado=round(deuda / cupo * 100, 1) if cupo else 0.0,
    )


# ── Ahorro ───────────────────────────────────────────────────────────────

def saldo_ahorro(registros) -> int:
    return sum(r["monto"] if r["tipo"] == "deposito" else -r["monto"] for r in registros)


def progreso_meta(saldo: int, meta: int) -> float:
    if meta <= 0:
        return 0.0
    return round(min(100, max(0, saldo / meta * 100)), 1)


def interes_ahorro(saldo: int, tasa_anual: float) -> tuple[int, int]:
    """Interés estimado (mensual, anual) para una tasa anual en %, ej. 4.6.

    La tasa mensual equivalente es (1 + tasa)^(1/12) - 1."""
    if saldo <= 0 or tasa_anual <= 0:
        return 0, 0
    r = tasa_anual / 100
    return round(saldo * ((1 + r) ** (1 / 12) - 1)), round(saldo * r)


DIAS_POR_PERIODO = {"dia": 365, "mes": 12, "anio": 1}


def tasa_diaria(tasa_anual: float) -> float:
    """Tasa diaria equivalente a una tasa anual efectiva en %: (1 + r)^(1/365) - 1."""
    return (1 + tasa_anual / 100) ** (1 / 365) - 1


def tasa_desde_pago(pago: float, saldo: int, periodo: str) -> float:
    """Tasa anual (%) a partir de lo que el banco paga. Ej: $15 al día sobre $240.000 → 2,31%.

    Supone que los intereses se capitalizan en cada período (día, mes o año)."""
    if saldo <= 0:
        raise ValueError("saldo")
    veces = DIAS_POR_PERIODO[periodo]
    return round(((1 + pago / saldo) ** veces - 1) * 100, 2)


def sumar_meses(mes: str, n: int) -> str:
    anio, num = map(int, mes.split("-"))
    total = anio * 12 + (num - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def calendario_cuotas(compras, hoy: date, meses: int = 12) -> dict[str, int]:
    """Cuánto se cobra en cuotas cada mes, desde el próximo mes.

    La cuota k de una compra se cobra k meses después del mes de compra
    (la primera, el mes siguiente). Devuelve {'AAAA-MM': monto} con `meses` entradas."""
    inicio = sumar_meses(hoy.strftime("%Y-%m"), 1)
    calendario = {sumar_meses(inicio, i): 0 for i in range(meses)}
    for c in compras:
        cuota = valor_cuota(c["monto"], c["cuotas"], _campo(c, "interes"))
        mes_compra = c["fecha"][:7]
        for k in range(1, c["cuotas"] + 1):
            mes = sumar_meses(mes_compra, k)
            if mes in calendario:
                calendario[mes] += cuota
    return calendario
