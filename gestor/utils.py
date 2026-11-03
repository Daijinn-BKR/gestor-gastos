"""Funciones de formato y validación reutilizables."""
import re
from datetime import date

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

CATEGORIAS = [
    "Alimentación", "Transporte", "Vivienda", "Servicios", "Salud",
    "Entretención", "Educación", "Ropa", "Sueldo", "Ahorro", "Otros",
]


class ErrorValidacion(ValueError):
    """Error con un mensaje apto para mostrar al usuario."""


def clp(valor) -> str:
    """15000 -> '$15.000'  ·  -2500 -> '-$2.500'"""
    numero = int(round(valor or 0))
    signo = "-" if numero < 0 else ""
    return f"{signo}${abs(numero):,}".replace(",", ".")


def fecha_corta(texto: str) -> str:
    """'2026-10-05' -> '05-10-2026'"""
    try:
        return date.fromisoformat(texto).strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        return texto


def dia_mes(fecha) -> str:
    """date(2026, 9, 21) -> '21 sep'"""
    return f"{fecha.day} {MESES[fecha.month - 1][:3]}"


def nombre_mes(mes: str) -> str:
    """'2026-10' -> 'octubre 2026'"""
    anio, num = mes.split("-")
    return f"{MESES[int(num) - 1]} {anio}"


def parse_monto(texto: str) -> int:
    """Acepta '15000', '15.000' o '$15.000'. Debe ser un entero positivo."""
    limpio = (texto or "").replace("$", "").replace(".", "").replace(" ", "").strip()
    if not limpio.isdigit() or int(limpio) <= 0:
        raise ErrorValidacion("El monto debe ser un número entero mayor que cero.")
    return int(limpio)


def usd(centavos) -> str:
    """1250 -> 'US$ 12,50'  ·  100000 -> 'US$ 1.000'  (sin decimales si son ,00)"""
    centavos = int(round(centavos or 0))
    signo = "-" if centavos < 0 else ""
    dolares, cent = divmod(abs(centavos), 100)
    texto = f"{dolares:,}".replace(",", ".")
    if cent:
        texto += f",{cent:02d}"
    return f"{signo}US$ {texto}"


def parse_usd(texto: str, campo: str = "Monto en dólares") -> int:
    """Acepta '100', '12,50', '12.50', 'US$ 1.234,50' o '1,234.50'. Devuelve centavos."""
    limpio = (texto or "").upper()
    for quitar in ("US$", "USD", "$", " "):
        limpio = limpio.replace(quitar, "")
    if "," in limpio and "." in limpio:
        # El separador que aparece último es el decimal; el otro es de miles
        miles = "." if limpio.rfind(",") > limpio.rfind(".") else ","
        limpio = limpio.replace(miles, "")
    elif limpio.count(".") > 1 or (limpio.count(".") == 1 and len(limpio.split(".")[1]) == 3):
        limpio = limpio.replace(".", "")  # '1.000' se lee como mil
    limpio = limpio.replace(",", ".")
    try:
        valor = round(float(limpio) * 100)
    except ValueError:
        raise ErrorValidacion(f"«{campo}» debe ser un número, por ejemplo 100 o 12,50.") from None
    if valor <= 0:
        raise ErrorValidacion(f"«{campo}» debe ser mayor que cero.")
    return valor


def parse_porcentaje(texto: str, campo: str, maximo: float = 100) -> float:
    """Acepta '4,6', '4.6' o '4,6%'. Vacío cuenta como 0."""
    limpio = (texto or "").replace("%", "").replace(" ", "").replace(",", ".").strip()
    if not limpio:
        return 0.0
    try:
        valor = float(limpio)
    except ValueError:
        raise ErrorValidacion(f"«{campo}» debe ser un número, por ejemplo 4,6.") from None
    if not 0 <= valor <= maximo:
        raise ErrorValidacion(f"«{campo}» debe estar entre 0 y {pct(maximo)}.")
    return round(valor, 2)


def pct(valor) -> str:
    """4.6 -> '4,6%'  ·  2.0 -> '2%'"""
    texto = f"{float(valor or 0):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") + "%"


def parse_fecha(texto: str) -> str:
    try:
        return date.fromisoformat(texto).isoformat()
    except (TypeError, ValueError):
        raise ErrorValidacion("La fecha no es válida.") from None


def parse_texto(texto: str, campo: str, obligatorio: bool = True, largo: int = 80) -> str:
    valor = (texto or "").strip()
    if obligatorio and not valor:
        raise ErrorValidacion(f"El campo «{campo}» es obligatorio.")
    return valor[:largo]


def mes_valido(texto: str | None) -> str:
    """Devuelve 'AAAA-MM' válido o el mes actual."""
    if texto and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", texto):
        return texto
    return date.today().strftime("%Y-%m")


def mover_mes(mes: str, delta: int) -> str:
    anio, num = map(int, mes.split("-"))
    total = anio * 12 + (num - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"
