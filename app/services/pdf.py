"""PDF de las plantillas, en Python puro: el .docx/.xlsx ya llenado se dibuja con reportlab (sin LibreOffice ni Word).

Word: párrafos (negrita, cursiva, subrayado, tachado, tamaño, color, fuente, fondo, alineación, sangrías,
espaciado e interlineado), viñetas y numeración, saltos de página, tablas (anchos, celdas combinadas, fondos,
bordes, alineación vertical, filas de encabezado), imágenes, encabezado y pie de página (con nº de página).
Excel: cada hoja con su rango usado (o su área de impresión), anchos y altos, celdas combinadas, fondos, bordes,
fuente, alineación y formatos de número; se ajusta al ancho de la página (horizontal si conviene).
No se dibujan: gráficos e imágenes de Excel, formas y cuadros de texto de Word. Las fórmulas de Excel se calculan
solo si son sencillas (FILA/ROW, SUMA/SUM, CONTAR, PROMEDIO, MIN, MAX, REDONDEAR y operaciones con celdas).
"""
import ast
import io
import operator
import os
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services import ErrorNegocio

EMU_POR_PT = 12700
TABULADOR = chr(0xE001)  # marca de un tabulador alineado (derecha o centro) dentro de un párrafo


def convertir_a_pdf(datos: bytes, extension: str) -> bytes:
    """Convierte un .docx o .xlsx (ya llenado) a PDF. Los errores se devuelven como ErrorNegocio."""
    if extension not in ("docx", "xlsx"):
        raise ErrorNegocio("Solo se convierten a PDF documentos Word (.docx) o Excel (.xlsx).")
    try:
        return _Word(datos).pdf() if extension == "docx" else _excel_a_pdf(datos)
    except ErrorNegocio:
        raise
    except Exception as e:  # archivo dañado o una construcción que no sabemos dibujar
        current_app.logger.exception("Fallo al convertir a PDF")
        raise ErrorNegocio("No se pudo convertir el documento a PDF. Revise el diseño de la plantilla.") from e


# ================================================================== fuentes
# Se usan las fuentes TrueType del sistema si están (Calibri, Arial…); si no, Vera, que viene con reportlab.
_ARCHIVOS_FUENTE = {
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "carlito": ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf"),
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "liberation sans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf",
                        "LiberationSans-BoldItalic.ttf"),
    "times new roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "liberation serif": ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf",
                         "LiberationSerif-BoldItalic.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    "segoe ui": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "trebuchet ms": ("trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf"),
    "century gothic": ("gothic.ttf", "gothicb.ttf", "gothici.ttf", "gothicbi.ttf"),
    "dejavu sans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
}
# Si la fuente pedida no está instalada, la más parecida que sí esté
_PARECIDAS = {"calibri": ["carlito"], "arial": ["liberation sans"], "helvetica": ["arial", "liberation sans"],
              "times new roman": ["liberation serif"], "cambria": ["times new roman", "liberation serif"],
              "aptos": ["calibri", "carlito"]}
_PREFERIDAS = ["calibri", "carlito", "arial", "liberation sans", "dejavu sans"]


@lru_cache(maxsize=1)
def _indice_fuentes() -> dict:
    """{nombre de archivo en minúsculas: ruta} de las carpetas de fuentes del sistema."""
    carpetas = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
                Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
                Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
                Path("/Library/Fonts"), Path("/System/Library/Fonts/Supplemental")]
    indice = {}
    for carpeta in carpetas:
        if carpeta.is_dir():
            for ruta in carpeta.rglob("*"):
                if ruta.suffix.lower() == ".ttf":
                    indice.setdefault(ruta.name.lower(), ruta)
    return indice


@lru_cache(maxsize=None)
def _registrar(familia: str) -> str | None:
    """Registra la familia (normal, negrita, cursiva, negrita cursiva) y devuelve su nombre en reportlab."""
    archivos = _ARCHIVOS_FUENTE.get(familia)
    if not archivos:
        return None
    indice = _indice_fuentes()
    rutas = [indice.get(a.lower()) for a in archivos]
    if rutas[0] is None:
        return None
    nombre = "F_" + re.sub(r"\W", "_", familia)
    variantes = []
    for sufijo, ruta in zip(("", "-B", "-I", "-BI"), rutas):
        try:
            pdfmetrics.registerFont(TTFont(nombre + sufijo, str(ruta or rutas[0])))
        except Exception:  # archivo de fuente ilegible: se usa la versión normal
            pdfmetrics.registerFont(TTFont(nombre + sufijo, str(rutas[0])))
        variantes.append(nombre + sufijo)
    pdfmetrics.registerFontFamily(nombre, normal=variantes[0], bold=variantes[1], italic=variantes[2],
                                  boldItalic=variantes[3])
    return nombre


@lru_cache(maxsize=1)
def _vera() -> str:
    for nombre, archivo in (("Vera", "Vera.ttf"), ("Vera-B", "VeraBd.ttf"), ("Vera-I", "VeraIt.ttf"),
                            ("Vera-BI", "VeraBI.ttf")):
        pdfmetrics.registerFont(TTFont(nombre, archivo))
    pdfmetrics.registerFontFamily("Vera", normal="Vera", bold="Vera-B", italic="Vera-I", boldItalic="Vera-BI")
    return "Vera"


@lru_cache(maxsize=None)
def fuente(nombre: str | None) -> str:
    """Nombre de familia reportlab para una fuente de Word/Excel (con reemplazo si no está instalada)."""
    clave = (nombre or "").strip().lower()
    for candidata in [clave, *_PARECIDAS.get(clave, []), *_PREFERIDAS]:
        if candidata and (registrada := _registrar(candidata)):
            return registrada
    return _vera()


def _color(valor) -> str | None:
    """'FF0000', 'FFFF0000' (ARGB) o RGBColor → '#ff0000'. None si es automático o no es un color."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if len(texto) == 8:
        texto = texto[2:]
    if re.fullmatch(r"[0-9A-Fa-f]{6}", texto):
        return "#" + texto.lower()
    return None


# ================================================================== Word
def _w(etiqueta: str) -> str:
    from docx.oxml.ns import qn

    return qn(etiqueta)


def _atr(elemento, ruta: str, atributo: str = "w:val"):
    """Atributo del nodo en 'w:pPr/w:jc' bajo el elemento; None si no está."""
    if elemento is None:
        return None
    nodo = elemento
    for parte in ruta.split("/"):
        nodo = nodo.find(_w(parte))
        if nodo is None:
            return None
    return nodo.get(_w(atributo))


class _Word:
    """Lee el .docx con python-docx y arma los elementos de reportlab en el mismo orden del documento."""

    def __init__(self, datos: bytes):
        import docx

        self.doc = docx.Document(io.BytesIO(datos))
        sec = self.doc.sections[0]
        largo = lambda v, defecto: v.pt if v is not None else defecto  # noqa: E731
        self.ancho_pag = largo(sec.page_width, A4[0])
        self.alto_pag = largo(sec.page_height, A4[1])
        self.margen = {lado: largo(getattr(sec, f"{lado}_margin"), 2.5 * cm)
                       for lado in ("left", "right", "top", "bottom")}
        self.dist_encabezado = largo(sec.header_distance, 1.25 * cm)
        self.dist_pie = largo(sec.footer_distance, 1.25 * cm)
        self.seccion = sec
        self.ancho_util = self.ancho_pag - self.margen["left"] - self.margen["right"]
        self._defectos()
        self._numeracion()
        self.contadores: dict = {}
        self.total_paginas = None
        self.pagina_actual = None  # al dibujar encabezado y pie: el nº de página que reemplaza a PAGE
        self.ancho_actual = self.ancho_util
        self.paginas = 0
        self.usa_total = False
        self.n_estilo = 0

    # ---------------------------------------------------------------- valores por defecto del documento
    def _defectos(self):
        estilos = self.doc.styles.element
        rpr = estilos.find(f"{_w('w:docDefaults')}/{_w('w:rPrDefault')}/{_w('w:rPr')}")
        ppr = estilos.find(f"{_w('w:docDefaults')}/{_w('w:pPrDefault')}/{_w('w:pPr')}")
        self.fuente_defecto = _atr(rpr, "w:rFonts", "w:ascii") or "Calibri"
        sz = _atr(rpr, "w:sz")
        self.tam_defecto = int(sz) / 2 if sz else 11.0
        self.esp_antes = int(_atr(ppr, "w:spacing", "w:before") or 0) / 20
        self.esp_despues = int(_atr(ppr, "w:spacing", "w:after") or 0) / 20
        linea = _atr(ppr, "w:spacing", "w:line")
        regla = _atr(ppr, "w:spacing", "w:lineRule")
        self.interlineado = int(linea) / 240 if linea and regla in (None, "auto") else 1.0

    def _numeracion(self):
        """{numId: {nivel: (formato, texto)}} para viñetas y listas numeradas."""
        self.formatos_lista = {}
        try:
            numeracion = self.doc.part.numbering_part.element
        except (KeyError, NotImplementedError, AttributeError):
            return
        abstractos = {}
        for a in numeracion.findall(_w("w:abstractNum")):
            niveles = {}
            for lvl in a.findall(_w("w:lvl")):
                niveles[lvl.get(_w("w:ilvl"))] = (_atr(lvl, "w:numFmt") or "bullet", _atr(lvl, "w:lvlText") or "•")
            abstractos[a.get(_w("w:abstractNumId"))] = niveles
        for n in numeracion.findall(_w("w:num")):
            self.formatos_lista[n.get(_w("w:numId"))] = abstractos.get(_atr(n, "w:abstractNumId"), {})

    # ---------------------------------------------------------------- herencia de estilos
    @staticmethod
    def _cadena(estilo):
        while estilo is not None:
            yield estilo
            estilo = estilo.base_style

    def _fmt_parrafo(self, p, atributo):
        valor = getattr(p.paragraph_format, atributo)
        if valor is not None:
            return valor
        for estilo in self._cadena(p.style):
            valor = getattr(estilo.paragraph_format, atributo)
            if valor is not None:
                return valor
        return None

    def _estilos_run(self, run, p):
        estilos = []
        try:
            if run.style is not None and run.style.style_id != "DefaultParagraphFont":
                estilos += list(self._cadena(run.style))
        except Exception:  # estilo de carácter inexistente
            pass
        return estilos + list(self._cadena(p.style))

    def _fmt_run(self, run, p, atributo):
        valor = getattr(run.font, atributo)
        if valor is not None:
            return valor
        for estilo in self._estilos_run(run, p):
            valor = getattr(estilo.font, atributo)
            if valor is not None:
                return valor
        return None

    def _color_run(self, run, p):
        for font in [run.font] + [e.font for e in self._estilos_run(run, p)]:
            try:
                if font.color is not None and font.color.type is not None and font.color.rgb is not None:
                    return _color(font.color.rgb)
            except Exception:  # color de tema sin RGB
                continue
        return None

    # ---------------------------------------------------------------- bloques (párrafos y tablas)
    def _bloques(self, contenedor, ancho, parte):
        """Párrafos y tablas de un cuerpo, celda, encabezado o pie, en orden."""
        from docx.table import Table as TablaDocx
        from docx.text.paragraph import Paragraph as ParrafoDocx

        salida = []
        for hijo in contenedor.iterchildren():
            if hijo.tag == _w("w:p"):
                salida += self._parrafo(ParrafoDocx(hijo, parte), ancho, parte)
            elif hijo.tag == _w("w:tbl"):
                salida += self._tabla(TablaDocx(hijo, parte), ancho, parte)
            elif hijo.tag in (_w("w:sdt"), _w("w:sdtContent"), _w("w:customXml")):
                salida += self._bloques(hijo, ancho, parte)
        return salida

    # ---------------------------------------------------------------- párrafo
    def _parrafo(self, p, ancho, parte):
        ppr = p._p.pPr
        estilo = self._estilo_parrafo(p, ppr)
        prefijo = self._vineta(p, ppr)
        salida = []
        salto = ppr.find(_w("w:pageBreakBefore")) if ppr is not None else None
        if salto is not None and salto.get(_w("w:val")) not in ("0", "false", "off"):
            salida.append(PageBreak())

        estado = {"piezas": [prefijo] if prefijo else [], "imagenes": [], "tam": 0.0}

        def cerrar(ultimo=False):
            texto = "".join(estado["piezas"])
            for img in estado["imagenes"]:
                img.hAlign = {TA_CENTER: "CENTER", TA_RIGHT: "RIGHT"}.get(estilo.alignment, "LEFT")
                salida.append(img)
            if texto.strip() or (not estado["imagenes"] and ultimo):
                st = estilo
                alto = estado["tam"] * 1.2 * self._linea(p)
                if alto > estilo.leading:
                    self.n_estilo += 1
                    st = ParagraphStyle(f"w{self.n_estilo}", parent=estilo, leading=alto)
                salida.append(self._con_tabuladores(texto, st, ancho) if TABULADOR in texto
                              else Paragraph(texto or "&nbsp;", st))
            estado.update(piezas=[], imagenes=[], tam=0.0)

        paradas = self._paradas_alineadas(p)
        campo = None  # dentro de un campo complejo (PAGE, NUMPAGES…): se reemplaza su resultado
        for r, run in self._runs(p):
            for nodo in r.iterchildren():
                etiqueta = nodo.tag
                if etiqueta == _w("w:fldChar"):
                    tipo = nodo.get(_w("w:fldCharType"))
                    if tipo == "begin":
                        campo = {"instr": "", "mostrar": True}
                    elif tipo == "separate" and campo is not None:
                        especial = self._campo(campo["instr"])
                        if especial is not None:
                            estado["piezas"].append(self._marcar(especial, run, p))
                            campo["mostrar"] = False
                    elif tipo == "end":
                        campo = None
                    continue
                if etiqueta == _w("w:instrText"):
                    if campo is not None:
                        campo["instr"] += nodo.text or ""
                    continue
                if campo is not None and not campo["mostrar"]:
                    continue
                if etiqueta == _w("w:t"):
                    estado["piezas"].append(self._marcar(escape(nodo.text or ""), run, p))
                    tam = self._fmt_run(run, p, "size")
                    estado["tam"] = max(estado["tam"], tam.pt if tam else self.tam_defecto)
                elif etiqueta == _w("w:tab"):
                    alineada = paradas.pop(0) if paradas else None
                    estado["piezas"].append(TABULADOR + alineada if alineada else "&nbsp;" * 6)
                elif etiqueta == _w("w:ptab"):
                    alineada = {"right": "R", "center": "C"}.get(nodo.get(_w("w:alignment")))
                    estado["piezas"].append(TABULADOR + alineada if alineada else "&nbsp;" * 6)
                elif etiqueta in (_w("w:br"), _w("w:cr")):
                    if nodo.get(_w("w:type")) == "page":
                        cerrar()
                        salida.append(PageBreak())
                    else:
                        estado["piezas"].append("<br/>")
                elif etiqueta == _w("w:drawing"):
                    estado["imagenes"] += self._imagenes(nodo, ancho, parte)
                elif etiqueta == _w("w:noBreakHyphen"):
                    estado["piezas"].append("-")
        cerrar(ultimo=True)
        return salida

    def _paradas_alineadas(self, p) -> list:
        """Alineación ('R', 'C' o None) de cada parada de tabulación del párrafo, en orden."""
        paradas = list(p.paragraph_format.tab_stops)
        if not paradas:
            for estilo in self._cadena(p.style):
                paradas = list(estilo.paragraph_format.tab_stops)
                if paradas:
                    break
        tipos = {"RIGHT": "R", "END": "R", "DECIMAL": "R", "CENTER": "C"}
        nombres = [getattr(t.alignment, "name", "") for t in paradas]
        return [tipos.get(n) for n in nombres if n != "CLEAR"]

    def _con_tabuladores(self, texto, estilo, ancho):
        """Un párrafo con tabuladores a la derecha o al centro: una fila con cada parte en su lugar."""
        celdas = []
        for i, trozo in enumerate(texto.split(TABULADOR)):
            alineacion = TA_LEFT if i == 0 else (TA_RIGHT if trozo[:1] == "R" else TA_CENTER)
            trozo = trozo if i == 0 else trozo[1:]
            self.n_estilo += 1
            st = ParagraphStyle(f"w{self.n_estilo}", parent=estilo, alignment=alineacion, spaceBefore=0,
                                spaceAfter=0, firstLineIndent=0, leftIndent=estilo.leftIndent if i == 0 else 0)
            celdas.append(Paragraph(trozo or "&nbsp;", st))
        t = Table([celdas], colWidths=[ancho / len(celdas)] * len(celdas))
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), estilo.spaceBefore),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), estilo.spaceAfter),
                               ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        return t

    def _runs(self, p):
        """(elemento w:r, Run), también los que están dentro de hipervínculos, campos simples y controles."""
        from docx.text.run import Run

        def recorrer(nodo):
            for hijo in nodo.iterchildren():
                if hijo.tag == _w("w:r"):
                    yield hijo, Run(hijo, p)
                elif hijo.tag == _w("w:fldSimple"):
                    especial = self._campo(hijo.get(_w("w:instr")) or "")
                    if especial is not None:
                        yield self._run_con_texto(especial, p, hijo.find(_w("w:r")))
                    else:
                        yield from recorrer(hijo)
                elif hijo.tag in (_w("w:hyperlink"), _w("w:smartTag"), _w("w:ins"), _w("w:sdt"),
                                  _w("w:sdtContent"), _w("w:customXml")):
                    yield from recorrer(hijo)

        yield from recorrer(p._p)

    @staticmethod
    def _run_con_texto(texto, p, original):
        """Un w:r nuevo con ese texto y el formato del run original (para los campos de nº de página)."""
        from copy import deepcopy

        from docx.text.run import Run
        from lxml import etree

        r = etree.SubElement(etree.Element(_w("w:p")), _w("w:r"))
        if original is not None and original.find(_w("w:rPr")) is not None:
            r.append(deepcopy(original.find(_w("w:rPr"))))
        etree.SubElement(r, _w("w:t")).text = texto
        return r, Run(r, p)

    def _campo(self, instruccion: str) -> str | None:
        partes = instruccion.split()
        codigo = partes[0].upper() if partes else ""
        if codigo == "PAGE":
            return str(self.pagina_actual or "")
        if codigo in ("NUMPAGES", "SECTIONPAGES"):
            self.usa_total = True
            return str(self.total_paginas or "")
        return None

    def _marcar(self, texto: str, run, p) -> str:
        """Texto de un run con su formato en el marcado de reportlab."""
        if not texto:
            return ""
        if self._fmt_run(run, p, "all_caps"):
            texto = texto.upper()
        tam = self._fmt_run(run, p, "size")
        attrs = [f'name="{fuente(self._fmt_run(run, p, "name") or self.fuente_defecto)}"',
                 f'size="{tam.pt if tam else self.tam_defecto:g}"']
        if (c := self._color_run(run, p)):
            attrs.append(f'color="{c}"')
        marcado = f"<font {' '.join(attrs)}>{texto}</font>"
        for atributo, etiqueta in (("bold", "b"), ("italic", "i"), ("underline", "u"), ("strike", "strike")):
            if self._fmt_run(run, p, atributo):
                marcado = f"<{etiqueta}>{marcado}</{etiqueta}>"
        if self._fmt_run(run, p, "superscript"):
            marcado = f"<super>{marcado}</super>"
        elif self._fmt_run(run, p, "subscript"):
            marcado = f"<sub>{marcado}</sub>"
        return marcado

    def _linea(self, p) -> float:
        valor = self._fmt_parrafo(p, "line_spacing")
        if valor is None:
            return self.interlineado
        if isinstance(valor, float):
            return valor
        return max(valor.pt / (self.tam_defecto * 1.2), 0.8)  # interlineado exacto en puntos

    def _estilo_parrafo(self, p, ppr) -> ParagraphStyle:
        alineacion = self._fmt_parrafo(p, "alignment")
        alineacion = {1: TA_CENTER, 2: TA_RIGHT, 3: TA_JUSTIFY}.get(int(alineacion) if alineacion is not None else 0,
                                                                     TA_LEFT)
        tam = next((e.font.size.pt for e in self._cadena(p.style) if e.font.size is not None), self.tam_defecto)
        nombre_fuente = next((e.font.name for e in self._cadena(p.style) if e.font.name), self.fuente_defecto)
        pt = lambda v, defecto=0.0: v.pt if v is not None else defecto  # noqa: E731
        sangria = pt(self._fmt_parrafo(p, "left_indent"))
        primera = pt(self._fmt_parrafo(p, "first_line_indent"))
        if self._num_id(p, ppr):
            sangria, primera = max(sangria, 18), min(primera, -12)
        fondo = _color(_atr(ppr, "w:shd", "w:fill"))
        self.n_estilo += 1
        return ParagraphStyle(
            f"w{self.n_estilo}", fontName=fuente(nombre_fuente), fontSize=tam, leading=tam * 1.2 * self._linea(p),
            alignment=alineacion, spaceBefore=pt(self._fmt_parrafo(p, "space_before"), self.esp_antes),
            spaceAfter=pt(self._fmt_parrafo(p, "space_after"), self.esp_despues),
            leftIndent=sangria, rightIndent=pt(self._fmt_parrafo(p, "right_indent")), firstLineIndent=primera,
            backColor=colors.HexColor(fondo) if fondo else None,
            keepWithNext=1 if self._fmt_parrafo(p, "keep_with_next") else 0,
        )

    def _num_id(self, p, ppr):
        num_id = _atr(ppr, "w:numPr/w:numId")
        if num_id is None:
            for estilo in self._cadena(p.style):
                num_id = _atr(estilo.element.pPr, "w:numPr/w:numId")
                if num_id is not None:
                    break
        return None if num_id in (None, "0") else num_id

    def _vineta(self, p, ppr) -> str:
        """Prefijo de viñeta o número de lista ('• ', '1. '), o ''."""
        num_id = self._num_id(p, ppr)
        if num_id is None:
            return ""
        nivel = _atr(ppr, "w:numPr/w:ilvl") or "0"
        formato, texto = self.formatos_lista.get(num_id, {}).get(nivel, ("bullet", "•"))
        if formato == "bullet":
            simbolo = texto if texto and ord(texto[0]) < 0xF000 else "•"  # los símbolos de Wingdings → «•»
            return f"{escape(simbolo)}&nbsp;&nbsp;"
        clave = (num_id, nivel)
        self.contadores[clave] = self.contadores.get(clave, 0) + 1
        for (n, lv) in list(self.contadores):  # al volver a un nivel se reinician los de abajo
            if n == num_id and int(lv) > int(nivel):
                del self.contadores[(n, lv)]
        valor = self.contadores[clave]
        if formato in ("lowerLetter", "upperLetter"):
            numero = chr(ord("a") + (valor - 1) % 26)
            numero = numero.upper() if formato == "upperLetter" else numero
        elif formato in ("lowerRoman", "upperRoman"):
            numero = _romano(valor)
            numero = numero.lower() if formato == "lowerRoman" else numero
        else:
            numero = str(valor)
        return escape(re.sub(r"%\d", numero, texto or "%1.")) + "&nbsp;&nbsp;"

    def _imagenes(self, dibujo, ancho, parte):
        salida = []
        extent = dibujo.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
        for blip in dibujo.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
            rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            if not rid or rid not in parte.related_parts:
                continue
            w = int(extent.get("cx")) / EMU_POR_PT if extent is not None else 200
            h = int(extent.get("cy")) / EMU_POR_PT if extent is not None else 150
            if w > ancho:
                w, h = ancho, h * ancho / w
            try:
                salida.append(Image(io.BytesIO(parte.related_parts[rid].blob), width=w, height=h))
            except Exception:  # formato que reportlab no lee (p. ej. EMF/WMF): se omite
                current_app.logger.warning("Imagen de Word omitida en el PDF (formato no soportado)")
        return salida

    # ---------------------------------------------------------------- tabla
    def _tabla(self, tabla, ancho, parte):
        tbl = tabla._tbl
        cols = [g.w.pt if g.w is not None else None for g in tbl.tblGrid.gridCol_lst] if tbl.tblGrid is not None else []
        if not cols:
            return []
        conocidas = sum(c for c in cols if c)
        faltan = [i for i, c in enumerate(cols) if not c]
        for i in faltan:
            cols[i] = max((ancho - conocidas) / len(faltan), 20)
        if sum(cols) > ancho:
            factor = ancho / sum(cols)
            cols = [c * factor for c in cols]
        n = len(cols)

        datos, comandos, inicio_vertical, encabezados = [], [], {}, 0
        for f, tr in enumerate(tbl.tr_lst):
            fila = [""] * n
            if tr.trPr is not None and tr.trPr.find(_w("w:tblHeader")) is not None and encabezados == f:
                encabezados += 1
            c = 0
            for tc in tr.tc_lst:
                if c >= n:
                    break
                tramo = min(tc.grid_span or 1, n - c)
                tcpr = tc.tcPr
                if tc.vMerge == "continue" and c in inicio_vertical:
                    inicio_vertical[c][1] = f  # la celda de arriba se estira hasta esta fila
                else:
                    fila[c] = self._bloques(tc, max(sum(cols[c:c + tramo]) - 8, 10), parte) or ""
                    if tramo > 1:
                        comandos.append(("SPAN", (c, f), (c + tramo - 1, f)))
                    if tc.vMerge == "restart":
                        inicio_vertical[c] = [f, f, tramo]
                    else:
                        inicio_vertical.pop(c, None)
                fondo = _color(_atr(tcpr, "w:shd", "w:fill"))
                if fondo:
                    comandos.append(("BACKGROUND", (c, f), (c + tramo - 1, f), colors.HexColor(fondo)))
                valign = {"center": "MIDDLE", "bottom": "BOTTOM"}.get(_atr(tcpr, "w:vAlign"), "TOP")
                comandos.append(("VALIGN", (c, f), (c + tramo - 1, f), valign))
                comandos += self._bordes_celda(tcpr, c, f, tramo)
                c += tramo
            datos.append(fila)
            # las combinaciones verticales que ya no siguen se cierran
            for col, (desde, hasta, tramo) in list(inicio_vertical.items()):
                if hasta < f:
                    del inicio_vertical[col]
            for col, (desde, hasta, tramo) in inicio_vertical.items():
                if hasta == f and desde < f:
                    comandos = [cmd for cmd in comandos if not (cmd[0] == "SPAN" and cmd[1] == (col, desde))]
                    comandos.append(("SPAN", (col, desde), (col + tramo - 1, hasta)))
        estilo = [("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        t = Table(datos, colWidths=cols, repeatRows=encabezados)
        t.setStyle(TableStyle(estilo + self._bordes_tabla(tbl) + comandos))
        t.hAlign = {"center": "CENTER", "right": "RIGHT", "end": "RIGHT"}.get(_atr(tbl.tblPr, "w:jc"), "LEFT")
        return [t, Spacer(1, 4)]

    @staticmethod
    def _linea_borde(nodo):
        if nodo is None or nodo.get(_w("w:val")) in (None, "nil", "none"):
            return None
        grosor = int(nodo.get(_w("w:sz")) or 4) / 8
        return max(grosor, 0.25), colors.HexColor(_color(nodo.get(_w("w:color"))) or "#000000")

    def _estilo_tabla(self, id_estilo):
        if not id_estilo:
            return None
        return self.doc.styles.element.find(f"{_w('w:style')}[@{_w('w:styleId')}='{id_estilo}']")

    def _bordes_tabla(self, tbl):
        """Bordes del propio tblPr o del estilo de la tabla (p. ej. «Tabla con cuadrícula»)."""
        nodo = tbl.tblPr.find(_w("w:tblBorders")) if tbl.tblPr is not None else None
        estilo = self._estilo_tabla(_atr(tbl.tblPr, "w:tblStyle"))
        while nodo is None and estilo is not None:
            nodo = estilo.find(f"{_w('w:tblPr')}/{_w('w:tblBorders')}")
            estilo = self._estilo_tabla(_atr(estilo, "w:basedOn"))
        if nodo is None:
            return []
        comandos = []
        for lado, cmd, desde, hasta in (("top", "LINEABOVE", (0, 0), (-1, 0)),
                                        ("bottom", "LINEBELOW", (0, -1), (-1, -1)),
                                        ("left", "LINEBEFORE", (0, 0), (0, -1)), ("start", "LINEBEFORE", (0, 0), (0, -1)),
                                        ("right", "LINEAFTER", (-1, 0), (-1, -1)), ("end", "LINEAFTER", (-1, 0), (-1, -1))):
            if (linea := self._linea_borde(nodo.find(_w(f"w:{lado}")))):
                comandos.append((cmd, desde, hasta, *linea))
        if (linea := self._linea_borde(nodo.find(_w("w:insideH")))):
            comandos.append(("LINEBELOW", (0, 0), (-1, -2), *linea))
        if (linea := self._linea_borde(nodo.find(_w("w:insideV")))):
            comandos.append(("LINEAFTER", (0, 0), (-2, -1), *linea))
        return comandos

    def _bordes_celda(self, tcpr, c, f, tramo):
        nodo = tcpr.find(_w("w:tcBorders")) if tcpr is not None else None
        if nodo is None:
            return []
        comandos = []
        for lado, cmd in (("top", "LINEABOVE"), ("bottom", "LINEBELOW"), ("left", "LINEBEFORE"),
                          ("start", "LINEBEFORE"), ("right", "LINEAFTER"), ("end", "LINEAFTER")):
            if (linea := self._linea_borde(nodo.find(_w(f"w:{lado}")))):
                comandos.append((cmd, (c, f), (c + tramo - 1, f), *linea))
        return comandos

    # ---------------------------------------------------------------- encabezado, pie y armado
    def _decorado(self, cual: str, pagina: int):
        sec = self.seccion
        primera = pagina == 1 and sec.different_first_page_header_footer
        if cual == "encabezado":
            obj = sec.first_page_header if primera else sec.header
        else:
            obj = sec.first_page_footer if primera else sec.footer
        if obj is None or obj.is_linked_to_previous:
            return []
        return self._bloques(obj._element, self.ancho_util, obj.part)

    def _dibujar_decorado(self, lienzo, doc):
        pagina = lienzo.getPageNumber()
        self.pagina_actual = pagina
        for cual in ("encabezado", "pie"):
            bloques = self._decorado(cual, pagina)
            if not bloques:
                continue
            medidas = [b.wrap(self.ancho_util, self.alto_pag) for b in bloques]
            y = self.alto_pag - self.dist_encabezado if cual == "encabezado" else self.dist_pie + sum(m[1] for m in medidas)
            for b, (ancho, alto) in zip(bloques, medidas):
                y -= alto
                x = self.margen["left"]
                if getattr(b, "hAlign", "LEFT") == "CENTER":
                    x += (self.ancho_util - ancho) / 2
                elif getattr(b, "hAlign", "LEFT") == "RIGHT":
                    x += self.ancho_util - ancho
                b.drawOn(lienzo, x, y)
        self.pagina_actual = None

    def pdf(self) -> bytes:
        contenido = self._construir()
        if self.usa_total:  # «Página X de Y»: hace falta saber cuántas páginas hay
            self.total_paginas = self.paginas
            contenido = self._construir()
        return contenido

    def _construir(self) -> bytes:
        self.contadores = {}
        cuerpo = self._bloques(self.doc.element.body, self.ancho_util, self.doc.part)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=(self.ancho_pag, self.alto_pag),
                                leftMargin=self.margen["left"], rightMargin=self.margen["right"],
                                topMargin=self.margen["top"], bottomMargin=self.margen["bottom"])
        doc.build(cuerpo or [Spacer(1, 1)], onFirstPage=self._dibujar_decorado, onLaterPages=self._dibujar_decorado)
        self.paginas = doc.page
        return buf.getvalue()


def _romano(n: int) -> str:
    salida = ""
    for valor, letras in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                          (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= valor:
            salida += letras
            n -= valor
    return salida


# ================================================================== Excel
_GROSOR_BORDE = {"hair": 0.25, "thin": 0.5, "dotted": 0.5, "dashed": 0.5, "dashDot": 0.5, "dashDotDot": 0.5,
                 "medium": 1.0, "mediumDashed": 1.0, "mediumDashDot": 1.0, "mediumDashDotDot": 1.0,
                 "slantDashDot": 1.0, "thick": 1.5, "double": 1.5}


def _excel_a_pdf(datos: bytes) -> bytes:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(datos))
    hojas = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
    margen = 1.5 * cm
    horizontal = any(ws.page_setup.orientation == "landscape" for ws in hojas)
    if horizontal or max((_ancho_hoja(ws) for ws in hojas), default=0) > A4[0] - 2 * margen:
        tam = landscape(A4)
    else:
        tam = A4
    elementos = []
    for ws in hojas:
        tabla = _hoja(ws, tam[0] - 2 * margen)
        if tabla is None:
            continue
        if elementos:
            elementos.append(PageBreak())
        elementos.append(tabla)
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=tam, leftMargin=margen, rightMargin=margen, topMargin=margen,
                      bottomMargin=margen).build(elementos or [Spacer(1, 1)])
    return buf.getvalue()


def _rango(ws):
    """(fila1, col1, fila2, col2) con contenido, o el área de impresión si la hoja la tiene."""
    from openpyxl.utils.cell import range_boundaries

    if ws.print_area:
        area = ws.print_area if isinstance(ws.print_area, str) else ws.print_area[0]
        c1, f1, c2, f2 = range_boundaries(area.split(",")[0].split("!")[-1].replace("$", ""))
        return f1, c1, f2, c2
    filas, cols = [], []
    for fila in ws.iter_rows():
        for c in fila:
            if c.value not in (None, "") or (c.fill is not None and c.fill.fill_type == "solid"):
                filas.append(c.row)
                cols.append(c.column)
    for rango in ws.merged_cells.ranges:
        filas += [rango.min_row, rango.max_row]
        cols += [rango.min_col, rango.max_col]
    if not filas:
        return None
    return min(filas), min(cols), max(filas), max(cols)


def _ancho_col(ws, col) -> float:
    from openpyxl.utils import get_column_letter

    dim = ws.column_dimensions.get(get_column_letter(col))
    if dim is not None and dim.hidden:
        return 0
    ancho = dim.width if dim is not None and dim.width else (ws.sheet_format.defaultColWidth or 8.43)
    return (ancho * 7 + 5) * 0.75  # caracteres → píxeles → puntos


def _ancho_hoja(ws) -> float:
    r = _rango(ws)
    return sum(_ancho_col(ws, c) for c in range(r[1], r[3] + 1)) if r else 0


def _hoja(ws, util: float):
    rango = _rango(ws)
    if rango is None:
        return None
    f1, c1, f2, c2 = rango
    columnas = [c for c in range(c1, c2 + 1) if _ancho_col(ws, c) > 0]
    filas = [f for f in range(f1, f2 + 1)
             if not (ws.row_dimensions.get(f) is not None and ws.row_dimensions[f].hidden)]
    if not columnas or not filas:
        return None
    anchos = [_ancho_col(ws, c) for c in columnas]
    escala = min(1.0, util / sum(anchos))
    anchos = [a * escala for a in anchos]
    pos_col = {c: i for i, c in enumerate(columnas)}
    pos_fila = {f: i for i, f in enumerate(filas)}
    combinadas, tapadas = {}, set()
    for r in ws.merged_cells.ranges:
        combinadas[(r.min_row, r.min_col)] = r
        tapadas |= {(f, c) for f in range(r.min_row, r.max_row + 1) for c in range(r.min_col, r.max_col + 1)} \
            - {(r.min_row, r.min_col)}
    formulas = _Formulas(ws)
    estilo = [("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
              ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
    datos, altos = [], []
    for f in filas:
        fila = []
        dim = ws.row_dimensions.get(f)
        altos.append(dim.height * escala if dim is not None and dim.height else None)
        for c in columnas:
            x, y = pos_col[c], pos_fila[f]
            if (f, c) in tapadas:
                fila.append("")
                continue
            celda = ws.cell(row=f, column=c)
            valor = formulas.valor(celda)
            fila.append(_parrafo_celda(celda, valor, escala) if valor not in (None, "") else "")
            x2, y2 = x, y
            if (comb := combinadas.get((f, c))):
                x2 = max((pos_col[k] for k in range(comb.min_col, comb.max_col + 1) if k in pos_col), default=x)
                y2 = max((pos_fila[k] for k in range(comb.min_row, comb.max_row + 1) if k in pos_fila), default=y)
                estilo.append(("SPAN", (x, y), (x2, y2)))
            if celda.fill is not None and celda.fill.fill_type == "solid":
                if (fondo := _color(getattr(celda.fill.fgColor, "rgb", None))):
                    estilo.append(("BACKGROUND", (x, y), (x2, y2), colors.HexColor(fondo)))
            estilo.append(("VALIGN", (x, y), (x2, y2), {"center": "MIDDLE", "top": "TOP"}.get(celda.alignment.vertical,
                                                                                               "BOTTOM")))
            for lado, cmd in (("top", "LINEABOVE"), ("bottom", "LINEBELOW"), ("left", "LINEBEFORE"),
                              ("right", "LINEAFTER")):
                borde = getattr(celda.border, lado)
                if borde is not None and borde.style:
                    color = _color(getattr(borde.color, "rgb", None) if borde.color is not None else None)
                    estilo.append((cmd, (x, y), (x2, y2), _GROSOR_BORDE.get(borde.style, 0.5),
                                   colors.HexColor(color or "#000000")))
        datos.append(fila)
    tabla = Table(datos, colWidths=anchos, rowHeights=altos if any(altos) else None)
    tabla.setStyle(TableStyle(estilo))
    tabla.hAlign = "LEFT"
    return tabla


def _parrafo_celda(celda, valor, escala: float) -> Paragraph:
    f = celda.font
    tam = max((f.sz or 11) * escala, 5)
    texto = escape(_formatear(valor, celda.number_format)).replace("\n", "<br/>")
    horizontal = celda.alignment.horizontal
    if horizontal in (None, "general"):
        es_numero = isinstance(valor, (int, float)) and not isinstance(valor, bool)
        alineacion = TA_RIGHT if es_numero else TA_LEFT
    else:
        alineacion = {"center": TA_CENTER, "centerContinuous": TA_CENTER, "right": TA_RIGHT,
                      "justify": TA_JUSTIFY}.get(horizontal, TA_LEFT)
    color = _color(getattr(f.color, "rgb", None) if f.color is not None else None)
    marcado = f'<font color="{color}">{texto}</font>' if color else texto
    for activo, etiqueta in ((f.b, "b"), (f.i, "i"), (f.u, "u"), (f.strike, "strike")):
        if activo:
            marcado = f"<{etiqueta}>{marcado}</{etiqueta}>"
    estilo = ParagraphStyle("celda", fontName=fuente(f.name), fontSize=tam, leading=tam * 1.2, alignment=alineacion)
    return Paragraph(marcado, estilo)


def _formatear(valor, formato: str | None) -> str:
    """Valor de una celda como lo mostraría Excel (formatos básicos; decimales con coma)."""
    formato = formato or "General"
    if isinstance(valor, bool):
        return "VERDADERO" if valor else "FALSO"
    if isinstance(valor, datetime):
        con_hora = (valor.hour or valor.minute) and "h" in formato.lower()
        return valor.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, (int, float)):
        if formato == "General":
            return str(int(valor)) if float(valor).is_integer() else f"{valor:.10g}".replace(".", ",")
        seccion = formato.split(";")[0]
        decimales = len(m.group(1)) if (m := re.search(r"\.([0#]+)", seccion)) else 0
        if "%" in seccion:
            return f"{valor * 100:.{decimales}f}".replace(".", ",") + " %"
        texto = f"{valor:,.{decimales}f}" if "," in seccion else f"{valor:.{decimales}f}"
        return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")  # 1.234,56
    return str(valor)


class _Formulas:
    """Calcula fórmulas sencillas (openpyxl no calcula). Si no puede, la celda queda vacía."""

    FUNCIONES = {
        "SUM": lambda *a: sum(_numeros(a)), "COUNT": lambda *a: len(_numeros(a)),
        "COUNTA": lambda *a: len([x for x in _plano(a) if x not in (None, "")]),
        "AVERAGE": lambda *a: (sum(_numeros(a)) / len(_numeros(a))) if _numeros(a) else 0,
        "MIN": lambda *a: min(_numeros(a), default=0), "MAX": lambda *a: max(_numeros(a), default=0),
        "ROUND": lambda x, n=0: round(_num(x), int(n)), "ABS": lambda x: abs(_num(x)),
    }
    OPERADORES = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
                  ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}

    def __init__(self, ws):
        self.ws = ws
        self.en_curso = set()

    def valor(self, celda):
        v = celda.value
        if isinstance(v, str) and v.startswith("="):
            return self._calcular(celda)
        return v

    def _calcular(self, celda):
        if celda.coordinate in self.en_curso:  # referencia circular
            return None
        self.en_curso.add(celda.coordinate)
        try:
            expr = celda.value[1:].replace("$", "")
            expr = re.sub(r"\b([A-Z]{1,3}\d+):([A-Z]{1,3}\d+)\b", r'_R("\1","\2")', expr)
            expr = re.sub(r'(?<!["\w])([A-Z]{1,3}\d+)\b(?!["(])', r'_C("\1")', expr)
            resultado = self._evaluar(ast.parse(expr.replace("^", "**"), mode="eval").body, celda)
            if resultado is None:  # como Excel: una referencia a una celda vacía muestra 0
                return 0
            return round(resultado, 10) if isinstance(resultado, float) else resultado
        except Exception:
            return None
        finally:
            self.en_curso.discard(celda.coordinate)

    def _evaluar(self, nodo, celda):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float, str)):
            return nodo.value
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in self.OPERADORES:
            izq, der = _num(self._evaluar(nodo.left, celda)), _num(self._evaluar(nodo.right, celda))
            return self.OPERADORES[type(nodo.op)](izq, der)
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in self.OPERADORES:
            return self.OPERADORES[type(nodo.op)](_num(self._evaluar(nodo.operand, celda)))
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and not nodo.keywords:
            nombre = nodo.func.id.upper()
            args = [self._evaluar(a, celda) for a in nodo.args]
            if nombre == "_C":
                return self.valor(self.ws[args[0]])
            if nombre == "_R":
                return [self.valor(c) for fila in self.ws[f"{args[0]}:{args[1]}"] for c in fila]
            if nombre == "ROW":
                return celda.row
            if nombre == "COLUMN":
                return celda.column
            if nombre in self.FUNCIONES:
                return self.FUNCIONES[nombre](*args)
        raise ValueError("fórmula no soportada")


def _plano(valores):
    for v in valores:
        if isinstance(v, list):
            yield from v
        else:
            yield v


def _numeros(valores):
    return [v for v in _plano(valores) if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _num(v):
    if v in (None, ""):
        return 0
    if isinstance(v, (int, float)):
        return v
    return float(str(v).replace(",", "."))
