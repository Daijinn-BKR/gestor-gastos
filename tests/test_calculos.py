from datetime import date

import pytest

from gestor.calculos import (estado_cuotas, meses_entre, progreso_meta,
                             resumen_credito, saldo_ahorro)
from gestor.utils import ErrorValidacion, clp, mover_mes, parse_monto


def test_clp():
    assert clp(15000) == "$15.000"
    assert clp(-2500) == "-$2.500"
    assert clp(0) == "$0"


@pytest.mark.parametrize("texto,esperado", [("15000", 15000), ("15.000", 15000), ("$ 1.250.000", 1250000)])
def test_parse_monto_valido(texto, esperado):
    assert parse_monto(texto) == esperado


@pytest.mark.parametrize("texto", ["", "abc", "0", "-500", "12,5"])
def test_parse_monto_invalido(texto):
    with pytest.raises(ErrorValidacion):
        parse_monto(texto)


def test_mover_mes_cruza_anio():
    assert mover_mes("2026-12", 1) == "2027-01"
    assert mover_mes("2026-01", -1) == "2025-12"


def test_meses_entre():
    assert meses_entre(date(2026, 8, 20), date(2026, 10, 1)) == 2


def test_estado_cuotas_primera_cuota_mes_siguiente():
    estado = estado_cuotas(90_000, 3, date(2026, 10, 15), date(2026, 10, 30))
    assert (estado.cuota, estado.facturadas, estado.restantes) == (30_000, 0, 3)

    estado = estado_cuotas(90_000, 3, date(2026, 8, 15), date(2026, 10, 30))
    assert (estado.facturadas, estado.restantes) == (2, 1)

    estado = estado_cuotas(90_000, 3, date(2025, 1, 1), date(2026, 10, 30))
    assert estado.restantes == 0


def test_resumen_credito():
    compras = [
        {"monto": 60_000, "cuotas": 3, "fecha": "2026-10-01"},
        {"monto": 40_000, "cuotas": 1, "fecha": "2026-10-05"},
    ]
    pagos = [{"monto": 10_000}]
    r = resumen_credito(compras, pagos, 500_000, date(2026, 10, 30))
    assert r.deuda == 90_000
    assert r.disponible == 410_000
    assert r.proxima_cuota == 60_000  # 20.000 de la primera + 40.000 de la segunda
    assert r.porcentaje_usado == 18.0


def test_saldo_y_meta_ahorro():
    registros = [{"tipo": "deposito", "monto": 100_000}, {"tipo": "retiro", "monto": 30_000}]
    assert saldo_ahorro(registros) == 70_000
    assert progreso_meta(70_000, 200_000) == 35.0
    assert progreso_meta(300_000, 200_000) == 100
    assert progreso_meta(10, 0) == 0


def test_ruta_db_fuera_del_proyecto(monkeypatch, tmp_path):
    from gestor import BASE_DIR, ruta_db
    monkeypatch.delenv("GESTOR_DB", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = ruta_db()
    assert ruta.endswith("gastos.db")
    assert str(BASE_DIR) not in ruta  # nunca dentro del repositorio

    monkeypatch.setenv("GESTOR_DB", "demo.db")
    assert ruta_db().endswith("demo.db")


def test_cuota_con_interes_sistema_frances():
    from gestor.calculos import total_a_pagar, valor_cuota
    assert valor_cuota(120_000, 12, 0) == 10_000
    # 100.000 en 12 cuotas al 2% mensual → cuota de $9.456
    assert valor_cuota(100_000, 12, 2) == 9_456
    assert total_a_pagar(100_000, 12, 2) == 9_456 * 12
    assert total_a_pagar(50_000, 1, 3) == 50_000  # sin cuotas, sin interés


def test_deuda_incluye_intereses():
    compras = [{"monto": 100_000, "cuotas": 12, "fecha": "2026-10-01", "interes": 2}]
    r = resumen_credito(compras, [], 500_000, date(2026, 10, 30))
    assert r.deuda == 9_456 * 12
    assert r.proxima_cuota == 9_456


def test_interes_ahorro():
    from gestor.calculos import interes_ahorro
    mensual, anual = interes_ahorro(1_000_000, 4.6)
    assert anual == 46_000
    assert 3_700 < mensual < 3_800   # (1,046)^(1/12) - 1 ≈ 0,375%
    assert interes_ahorro(0, 4.6) == (0, 0)


def test_porcentajes():
    from gestor.utils import parse_porcentaje, pct
    assert parse_porcentaje("4,6", "Tasa") == 4.6
    assert parse_porcentaje("2.1%", "Tasa") == 2.1
    assert parse_porcentaje("", "Tasa") == 0
    with pytest.raises(ErrorValidacion):
        parse_porcentaje("-1", "Tasa")
    assert pct(4.6) == "4,6%"
    assert pct(2.0) == "2%"


def test_dolares():
    from gestor.utils import parse_usd, usd
    assert parse_usd("100") == 10_000
    assert parse_usd("12,50") == 1_250
    assert parse_usd("12.50") == 1_250
    assert parse_usd("US$ 1.234,50") == 123_450
    assert parse_usd("1,234.50") == 123_450
    assert usd(1_250) == "US$ 12,50"
    assert usd(100_000) == "US$ 1.000"
    with pytest.raises(ErrorValidacion):
        parse_usd("abc")
