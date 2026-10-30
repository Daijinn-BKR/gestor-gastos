-- Esquema de la base de datos (versión 3).
-- Usa IF NOT EXISTS para poder ejecutarse en cada arranque.
-- Las bases creadas con versiones anteriores se actualizan en db.py.
-- Montos en pesos: enteros. Montos en dólares: enteros en CENTAVOS (US$ 12,50 → 1250).

-- 1) Ingresos y egresos de la cuenta principal
CREATE TABLE IF NOT EXISTS movimientos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT    NOT NULL,                       -- formato AAAA-MM-DD
    tipo        TEXT    NOT NULL CHECK (tipo IN ('ingreso', 'egreso')),
    categoria   TEXT    NOT NULL,
    descripcion TEXT    NOT NULL DEFAULT '',
    monto       INTEGER NOT NULL CHECK (monto > 0)      -- en pesos, sin decimales
);

-- 2) Crédito: una o más cuentas (ej. Falabella, BCI), con sus compras y pagos
CREATE TABLE IF NOT EXISTS credito_cuentas (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT    NOT NULL,
    cupo     INTEGER NOT NULL DEFAULT 0 CHECK (cupo >= 0),
    cupo_usd INTEGER NOT NULL DEFAULT 0 CHECK (cupo_usd >= 0)   -- 0 = sin cupo internacional
);

CREATE TABLE IF NOT EXISTS credito_compras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT    NOT NULL,
    categoria   TEXT    NOT NULL,
    descripcion TEXT    NOT NULL DEFAULT '',
    monto       INTEGER NOT NULL CHECK (monto > 0),
    cuotas      INTEGER NOT NULL DEFAULT 1 CHECK (cuotas BETWEEN 1 AND 48),
    cuenta_id   INTEGER REFERENCES credito_cuentas(id) ON DELETE CASCADE,
    interes     REAL    NOT NULL DEFAULT 0 CHECK (interes >= 0),  -- % mensual
    moneda      TEXT    NOT NULL DEFAULT 'CLP' CHECK (moneda IN ('CLP', 'USD'))
);

CREATE TABLE IF NOT EXISTS credito_pagos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha         TEXT    NOT NULL,
    descripcion   TEXT    NOT NULL DEFAULT '',
    monto         INTEGER NOT NULL CHECK (monto > 0),
    movimiento_id INTEGER REFERENCES movimientos(id) ON DELETE SET NULL,
    cuenta_id     INTEGER REFERENCES credito_cuentas(id) ON DELETE CASCADE,
    moneda        TEXT    NOT NULL DEFAULT 'CLP' CHECK (moneda IN ('CLP', 'USD')),
    monto_clp     INTEGER                 -- pagos en USD: cuántos pesos costó (opcional)
);

-- 3) Cuenta de ahorro: depósitos y retiros
CREATE TABLE IF NOT EXISTS ahorro (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha         TEXT    NOT NULL,
    tipo          TEXT    NOT NULL CHECK (tipo IN ('deposito', 'retiro')),
    descripcion   TEXT    NOT NULL DEFAULT '',
    monto         INTEGER NOT NULL CHECK (monto > 0),
    movimiento_id INTEGER REFERENCES movimientos(id) ON DELETE SET NULL
);

-- Ajustes simples (meta de ahorro, tasa anual)
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
