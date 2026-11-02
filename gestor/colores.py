"""Color de acento elegido por el usuario.

A partir de un solo color calcula las variantes que necesita la interfaz, cuidando que
el texto siempre se lea bien (contraste mínimo 4,5:1, como pide la norma WCAG AA):
- primario:        relleno de botones, barras y pestañas activas (el color elegido)
- texto_claro:     el mismo tono, oscurecido si hace falta, para texto sobre fondo claro
- texto_oscuro:    el mismo tono, aclarado si hace falta, para texto sobre fondo oscuro
- sobre_primario:  texto encima del relleno (casi negro o blanco, el que se lea mejor)
"""
import colorsys
import re

COLOR_POR_DEFECTO = "#F2A5EA"

# Colores listos para elegir con un clic
PREDEFINIDOS = [
    ("#F2A5EA", "Rosado"),
    ("#2F6FED", "Azul"),
    ("#1F9D55", "Verde"),
    ("#8E44AD", "Morado"),
    ("#E8833A", "Naranjo"),
    ("#D64545", "Rojo"),
    ("#138F8F", "Turquesa"),
    ("#5B6475", "Gris"),
]

FONDO_CLARO = "#F5F6F8"
SUPERFICIE_OSCURA = "#1B2029"


def es_color(texto: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", texto or ""))


def _rgb(hexa: str) -> tuple[int, int, int]:
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def luminancia(hexa: str) -> float:
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rgb(hexa))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mezclar(hexa: str, con: str, cantidad: float) -> str:
    a, b = _rgb(hexa), _rgb(con)
    return _hex(x + (y - x) * cantidad for x, y in zip(a, b))


def _ajustar(hexa: str, fondo: str, hacia: str, minimo: float = 4.5) -> str:
    """Oscurece o aclara el color (mismo tono y saturación) hasta que contraste con el fondo."""
    r, g, b = (c / 255 for c in _rgb(hexa))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    destino = 0.0 if hacia == "#000000" else 1.0
    for paso in range(0, 101, 2):
        nueva_l = l + (destino - l) * paso / 100
        candidato = _hex(c * 255 for c in colorsys.hls_to_rgb(h, nueva_l, s))
        if contraste(candidato, fondo) >= minimo:
            return candidato
    return hacia


# El rosado original tiene tonos elegidos a mano; se mantienen tal cual.
PALETA_POR_DEFECTO = {"primario": "#F2A5EA", "texto_claro": "#A0368F",
                      "texto_oscuro": "#F2A5EA", "sobre_primario": "#3A1036"}


def paleta(color: str) -> dict:
    color = color.upper() if es_color(color) else COLOR_POR_DEFECTO
    if color == COLOR_POR_DEFECTO:
        return dict(PALETA_POR_DEFECTO)
    oscuro_sobre = _mezclar(color, "#000000", 0.78)       # casi negro, con un toque del color
    sobre = oscuro_sobre if contraste(color, oscuro_sobre) >= contraste(color, "#FFFFFF") else "#FFFFFF"
    return {
        "primario": color,
        "texto_claro": _ajustar(color, FONDO_CLARO, "#000000"),
        "texto_oscuro": _ajustar(color, SUPERFICIE_OSCURA, "#FFFFFF"),
        "sobre_primario": sobre,
    }


# Colores para los demás créditos en los gráficos: (modo claro, modo oscuro)
SERIES = [
    ("#1F9D55", "#4CC983"), ("#C98A00", "#F0B429"), ("#8E44AD", "#C08CF0"),
    ("#D64545", "#FF7A7A"), ("#138F8F", "#4FD1D1"), ("#2F6FED", "#6B9BFF"),
    ("#D63AA8", "#F2A5EA"),
]


def _tono(hexa: str) -> float:
    r, g, b = (c / 255 for c in _rgb(hexa))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def _saturacion(hexa: str) -> float:
    r, g, b = (c / 255 for c in _rgb(hexa))
    return colorsys.rgb_to_hls(r, g, b)[2]


def series(color: str) -> list[tuple[str, str]]:
    """5 colores para los otros créditos, evitando los que se parezcan al color elegido."""
    color = color.upper() if es_color(color) else COLOR_POR_DEFECTO
    if _saturacion(color) < 0.15:          # grises: cualquier color de la lista sirve
        return SERIES[:5]
    def distancia(c):
        d = abs(_tono(c[0]) - _tono(color)) % 360
        return min(d, 360 - d)
    return [c for c in SERIES if distancia(c) >= 35][:5]


def css(color: str) -> str:
    """Variables CSS que reemplazan las del tema por defecto."""
    p = paleta(color)
    claro = (f"--primario: {p['primario']}; --primario-texto: {p['texto_claro']}; "
             f"--sobre-primario: {p['sobre_primario']}; --serie-0: {p['primario']};")
    oscuro = (f"--primario: {p['primario']}; --primario-texto: {p['texto_oscuro']}; "
              f"--sobre-primario: {p['sobre_primario']}; --serie-0: {p['primario']};")
    otros = series(color)
    claro += " " + " ".join(f"--serie-{i}: {c};" for i, (c, _) in enumerate(otros, start=1))
    oscuro += " " + " ".join(f"--serie-{i}: {c};" for i, (_, c) in enumerate(otros, start=1))
    # Modo oscuro: forzado en Ajustes (data-tema="oscuro") o automático según Windows
    return (f":root {{ {claro} }}\n"
            f':root[data-tema="oscuro"] {{ {oscuro} }}\n'
            f'@media (prefers-color-scheme: dark) {{ :root:not([data-tema="claro"]) {{ {oscuro} }} }}')
