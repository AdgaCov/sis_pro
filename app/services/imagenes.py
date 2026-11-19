"""Imágenes PNG de los gráficos del tablero, para insertarlas en plantillas Word.

Se dibujan con Pillow (dependencia de reportlab), sin JavaScript ni librerías extra. Reciben los
mismos datos que la vista Gráficos (`services.graficos.datos`), así que muestran lo mismo.
"""
import io
import math
from functools import lru_cache
from pathlib import Path

import reportlab
from PIL import Image, ImageDraw, ImageFont

ESCALA = 2  # se dibuja al doble y se reduce: bordes suaves
FONDO = "#FFFFFF"
TEXTO = "#3A4256"
SUAVE = "#5B6478"
REJILLA = "#E3E7EF"
AZUL = "#1F3864"
AZUL2 = "#2E4A7D"
VERDE = "#3B9A63"
ROJO = "#B42318"
GRIS = "#DDE2EC"


# Bitstream Vera viene con reportlab y tiene tildes, ñ y º (la fuente por defecto de Pillow no).
_VERA = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


@lru_cache(maxsize=16)
def _fuente(tam: int):
    try:
        return ImageFont.truetype(str(_VERA), tam * ESCALA)
    except OSError:
        return ImageFont.load_default(size=tam * ESCALA)


def _lienzo(ancho: int, alto: int):
    img = Image.new("RGB", (ancho * ESCALA, alto * ESCALA), FONDO)
    return img, ImageDraw.Draw(img)


def _png(img) -> bytes:
    img = img.resize((img.width // ESCALA, img.height // ESCALA), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _texto(d, xy, texto, tam=11, color=TEXTO, ancla="la"):
    d.text((xy[0] * ESCALA, xy[1] * ESCALA), str(texto), fill=color, font=_fuente(tam), anchor=ancla)


def _rect(d, x0, y0, x1, y1, color):
    d.rectangle([x0 * ESCALA, y0 * ESCALA, x1 * ESCALA, y1 * ESCALA], fill=color)


def _linea(d, puntos, color, ancho=1):
    d.line([(x * ESCALA, y * ESCALA) for x, y in puntos], fill=color, width=ancho * ESCALA)


def _sin_datos(ancho, alto, mensaje="Sin datos") -> bytes:
    img, d = _lienzo(ancho, alto)
    _texto(d, (ancho / 2, alto / 2), mensaje, 12, SUAVE, "mm")
    return _png(img)


def _escala_y(maximo: int) -> tuple[int, int]:
    """Tope y paso enteros para el eje Y."""
    maximo = max(1, maximo)
    paso = max(1, math.ceil(maximo / 5))
    return paso * math.ceil(maximo / paso), paso


def _ejes_y(d, x0, y0, x1, y1, tope, paso):
    v = 0
    while v <= tope:
        y = y1 - (y1 - y0) * v / tope
        _linea(d, [(x0, y), (x1, y)], REJILLA)
        _texto(d, (x0 - 6, y), v, 9, SUAVE, "rm")
        v += paso


def _leyenda(d, items, x, y):
    for etiqueta, color in items:
        _rect(d, x, y, x + 10, y + 10, color)
        _texto(d, (x + 14, y + 5), etiqueta, 9, SUAVE, "lm")
        x += 22 + len(etiqueta) * 6


def barras_por_unidad(barras: dict, ancho=640, alto=300) -> bytes:
    """Barras apiladas: pendientes por unidad, divididas por alerta."""
    etiquetas, series = barras["etiquetas"], barras["series"]
    totales = [sum(s["valores"][k] for s in series) for k in range(len(etiquetas))]
    if not etiquetas or not any(totales):
        return _sin_datos(ancho, alto, "Sin tareas pendientes")
    img, d = _lienzo(ancho, alto)
    x0, y0, x1, y1 = 40, 34, ancho - 12, alto - 28
    tope, paso = _escala_y(max(totales))
    _ejes_y(d, x0, y0, x1, y1, tope, paso)
    _leyenda(d, [(s["alerta"], s["color"]) for s in series], x0, 8)
    hueco = (x1 - x0) / len(etiquetas)
    for k, etiqueta in enumerate(etiquetas):
        xa, xb = x0 + hueco * k + hueco * 0.18, x0 + hueco * (k + 1) - hueco * 0.18
        base = y1
        for s in series:
            v = s["valores"][k]
            if v:
                alto_b = (y1 - y0) * v / tope
                _rect(d, xa, base - alto_b, xb, base, s["color"])
                base -= alto_b
        _texto(d, ((xa + xb) / 2, y1 + 6), etiqueta, 9, SUAVE, "ma")
    return _png(img)


def velocimetro(cumplimiento: dict, ancho=320, alto=190) -> bytes:
    """Media dona con el % de concluidas a tiempo y la marca de la meta."""
    pct, meta = cumplimiento.get("pct"), cumplimiento.get("meta", 80)
    if pct is None:
        return _sin_datos(ancho, alto, "Sin tareas concluidas con fecha límite")
    img, d = _lienzo(ancho, alto)
    cx, cy, r, grosor = ancho / 2, alto - 40, min(ancho / 2 - 20, alto - 60), 26
    caja = [(cx - r) * ESCALA, (cy - r) * ESCALA, (cx + r) * ESCALA, (cy + r) * ESCALA]
    d.arc(caja, 180, 360, fill=GRIS, width=grosor * ESCALA)
    if pct > 0:
        d.arc(caja, 180, 180 + 180 * pct / 100, fill=VERDE if pct >= meta else ROJO, width=grosor * ESCALA)
    ang = math.pi + math.pi * meta / 100
    interior, exterior = r - grosor - 4, r + 6
    _linea(d, [(cx + math.cos(ang) * interior, cy + math.sin(ang) * interior),
               (cx + math.cos(ang) * exterior, cy + math.sin(ang) * exterior)], AZUL, 3)
    _texto(d, (cx, cy - 6), f"{pct} %", 22, VERDE if pct >= meta else ROJO, "ms")
    _texto(d, (cx, cy + 16), f"Meta {meta} % · {cumplimiento.get('base', 0)} concluidas con fecha límite", 9,
           SUAVE, "ma")
    return _png(img)


def creadas_concluidas(mensual: dict, ancho=640, alto=260) -> bytes:
    """Líneas: tareas creadas y concluidas por mes."""
    etiquetas = mensual["etiquetas"]
    series = [("Creadas", mensual["creadas"], AZUL2), ("Concluidas", mensual["concluidas"], VERDE)]
    img, d = _lienzo(ancho, alto)
    x0, y0, x1, y1 = 40, 30, ancho - 26, alto - 28
    tope, paso = _escala_y(max([*mensual["creadas"], *mensual["concluidas"], 0]))
    _ejes_y(d, x0, y0, x1, y1, tope, paso)
    _leyenda(d, [(n, c) for n, _, c in series], x0, 8)
    n = max(1, len(etiquetas) - 1)
    xs = [x0 + (x1 - x0) * k / n for k in range(len(etiquetas))]
    for k, e in enumerate(etiquetas):
        _texto(d, (xs[k], y1 + 6), e, 8, SUAVE, "ma")
    for _, valores, color in series:
        puntos = [(xs[k], y1 - (y1 - y0) * v / tope) for k, v in enumerate(valores)]
        _linea(d, puntos, color, 2)
        for x, y in puntos:
            d.ellipse([(x - 3) * ESCALA, (y - 3) * ESCALA, (x + 3) * ESCALA, (y + 3) * ESCALA], fill=color)
    return _png(img)


def embudo(filas: list, ancho=640, alto=None) -> bytes:
    """Barras horizontales: tareas abiertas por estado, en el orden del catálogo."""
    if not filas:
        return _sin_datos(ancho, 80, "Sin tareas abiertas")
    alto = alto or 30 + 26 * len(filas)
    img, d = _lienzo(ancho, alto)
    x0, x1 = 230, ancho - 40
    maximo = max(f["valor"] for f in filas) or 1
    for k, f in enumerate(filas):
        y = 14 + 26 * k
        _texto(d, (x0 - 8, y + 9), f["estado"][:38], 9, TEXTO, "rm")
        largo = (x1 - x0) * f["valor"] / maximo
        _rect(d, x0, y, x0 + max(largo, 2), y + 18, AZUL2)
        _texto(d, (x0 + largo + 6, y + 9), f["valor"], 9, TEXTO, "lm")
    return _png(img)


def todas(datos: dict) -> dict[str, bytes]:
    """Las cuatro imágenes del tablero, por nombre de marcador (imagen.xxx)."""
    return {
        "barras": barras_por_unidad(datos["barras"]),
        "cumplimiento": velocimetro(datos["cumplimiento"]),
        "mensual": creadas_concluidas(datos["mensual"]),
        "embudo": embudo(datos["embudo"]),
    }
