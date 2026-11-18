"""PDF: el resumen ejecutivo se genera con reportlab; las plantillas Word/Excel se convierten con LibreOffice."""
import io
import shutil
import subprocess
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services import ErrorNegocio
from app.utils.fechas import formato_fecha

AZUL = colors.HexColor("#1F3864")
GRIS = colors.HexColor("#5B6478")
BORDE = colors.HexColor("#BBC2D0")
FONDO_CAB = colors.HexColor("#E8EEF8")
ROJO = colors.HexColor("#B42318")
COLOR_ALERTA = {
    "VENCIDO": ROJO, "CRÍTICO": colors.HexColor("#D9534F"), "POR VENCER": colors.HexColor("#9A5B00"),
    "SEGUIMIENTO": colors.HexColor("#9A5B00"), "EN CURSO": AZUL, "CONCLUIDO": colors.HexColor("#1E7A46"),
    "SIN FECHA": GRIS,
}

_base = getSampleStyleSheet()
E = {
    "titulo": ParagraphStyle("titulo", parent=_base["Title"], fontSize=14, leading=17, textColor=AZUL, alignment=0,
                             spaceAfter=2),
    "sub": ParagraphStyle("sub", parent=_base["Normal"], fontSize=8, textColor=GRIS, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontSize=10, textColor=AZUL, spaceBefore=10, spaceAfter=4),
    "celda": ParagraphStyle("celda", parent=_base["Normal"], fontSize=7, leading=8.5),
    "celda_cab": ParagraphStyle("celda_cab", parent=_base["Normal"], fontSize=7, leading=8.5,
                                fontName="Helvetica-Bold", textColor=AZUL),
    "num": ParagraphStyle("num", parent=_base["Normal"], fontSize=8, leading=10, alignment=TA_RIGHT),
    "kpi_et": ParagraphStyle("kpi_et", parent=_base["Normal"], fontSize=7, textColor=GRIS, leading=8),
    "kpi_val": ParagraphStyle("kpi_val", parent=_base["Normal"], fontSize=15, leading=18, fontName="Helvetica-Bold",
                              textColor=AZUL),
    "pie": ParagraphStyle("pie", parent=_base["Normal"], fontSize=7, textColor=GRIS),
}


def _p(texto, estilo="celda") -> Paragraph:
    return Paragraph(escape(str(texto if texto not in (None, "") else "—")).replace("\n", "<br/>"), E[estilo])


def _tabla(filas, anchos, cabecera=True, alinear_derecha_desde=None) -> Table:
    t = Table(filas, colWidths=anchos, repeatRows=1 if cabecera else 0)
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if cabecera:
        estilo.append(("BACKGROUND", (0, 0), (-1, 0), FONDO_CAB))
    if alinear_derecha_desde is not None:
        estilo.append(("ALIGN", (alinear_derecha_desde, 0), (-1, -1), "RIGHT"))
    t.setStyle(TableStyle(estilo))
    return t


def _pie(lienzo, doc, texto):
    lienzo.saveState()
    lienzo.setFont("Helvetica", 7)
    lienzo.setFillColor(GRIS)
    lienzo.drawString(doc.leftMargin, 8 * mm, texto)
    lienzo.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f"Página {doc.page}")
    lienzo.restoreState()


def resumen_ejecutivo(datos: dict, detalle: list, alcance: str, filtros: str, generado: str) -> bytes:
    """PDF del resumen ejecutivo. `datos` viene de services.resumen.resumen_ejecutivo; `detalle`, de filtrar()."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=14 * mm,
                            title="Resumen ejecutivo · Gestiones con el MRE", author="Bolivia en el Mundo")
    ancho = doc.width
    h = []
    h.append(Paragraph("BOLIVIA EN EL MUNDO · RESUMEN EJECUTIVO · GESTIONES CON EL MRE", E["titulo"]))
    h.append(Paragraph(escape(f"{alcance} · {generado}"), E["sub"]))

    # Indicadores
    kpis = datos["kpis"]
    celdas = [[Paragraph(escape(k.upper()), E["kpi_et"]) for k, _, _ in kpis],
              [Paragraph(str(v), ParagraphStyle("v", parent=E["kpi_val"], textColor=ROJO if r and v else AZUL))
               for _, v, r in kpis]]
    t = Table(celdas, colWidths=[ancho / len(kpis)] * len(kpis))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, BORDE), ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    h.append(t)

    # Por unidad
    filas = [[_p(c, "celda_cab") for c in ("Unidad", "Total", "Pendientes", "Vencidas", "Alta pend.",
                                           "Sin respuesta", "Concluidas")]]
    for r in datos["por_unidad"]:
        filas.append([_p(r["unidad"].nombre)] +
                     [_p(r[k], "num") for k in ("total", "pendientes", "vencidas", "alta", "sin_respuesta",
                                                "concluidas")])
    h.append(KeepTogether([Paragraph("Gestiones por unidad", E["h2"]),
                           _tabla(filas, [ancho * 0.4] + [ancho * 0.1] * 6)]))

    # Por instancia y por tipo, lado a lado
    def mini(titulo, pares, ancho_t):
        f = [[_p(titulo, "celda_cab"), _p("Pendientes", "celda_cab")]]
        f += [[_p(n), _p(c, "num")] for n, c in pares] or [[_p("Sin pendientes."), _p("")]]
        return _tabla(f, [ancho_t * 0.8, ancho_t * 0.2])

    lado = (ancho - 8 * mm) / 2
    dos = Table([[mini("Instancia del MRE", datos["por_instancia"], lado), mini("Tipo", datos["por_tipo"], lado)]],
                colWidths=[lado + 4 * mm, lado + 4 * mm])
    dos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm)]))
    h.append(KeepTogether([Paragraph("Pendientes por instancia y por tipo", E["h2"]), dos]))

    # Detalle
    h.append(Paragraph(escape(f"Detalle consolidado · {len(detalle)} gestiones"), E["h2"]))
    if filtros:
        h.append(Paragraph(escape(filtros), E["sub"]))
    cab = ("Código", "Unidad", "Tipo", "Tarea / asunto", "Instancia", "Responsable", "Inicio", "Límite",
           "Estado", "Alerta", "Resultado")
    proporciones = (0.07, 0.06, 0.08, 0.185, 0.1, 0.11, 0.055, 0.055, 0.09, 0.08, 0.105)
    filas = [[_p(c, "celda_cab") for c in cab]]
    for i in detalle:
        t = i.t
        resp = ""
        if t.responsable:
            resp = t.responsable.nombre + (f"\n{t.responsable.persona}" if t.responsable.persona else "")
        alerta = Paragraph(f'<font color="{COLOR_ALERTA.get(i.alerta, GRIS).hexval()}"><b>{escape(i.alerta)}</b></font>',
                           E["celda"])
        filas.append([
            _p(t.codigo), _p(t.unidad.sigla), _p(t.tipo.valor), _p(t.asunto),
            _p(t.instancia.valor if t.instancia else ""), _p(resp or "Sin asignar"),
            _p(formato_fecha(t.fecha_solicitud)), _p(formato_fecha(t.fecha_limite)), _p(t.estado.valor), alerta,
            _p(t.resultado),
        ])
    if len(filas) == 1:
        filas.append([_p("Sin gestiones con el MRE para mostrar.")] + [_p("")] * (len(cab) - 1))
    h.append(_tabla(filas, [ancho * p for p in proporciones]))

    h.append(Spacer(1, 6))
    h.append(Paragraph("Seguimiento de tareas y trámites con el MRE · Las tareas internas no se incluyen.", E["pie"]))
    pie = f"Resumen ejecutivo · {generado}"
    doc.build(h, onFirstPage=lambda c, d: _pie(c, d, pie), onLaterPages=lambda c, d: _pie(c, d, pie))
    return buf.getvalue()


def _documento(buf, titulo: str):
    return SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                             topMargin=12 * mm, bottomMargin=14 * mm, title=titulo, author="Bolivia en el Mundo")


def _kpis(kpis, ancho) -> Table:
    celdas = [[Paragraph(escape(k.upper()), E["kpi_et"]) for k, _, _ in kpis],
              [Paragraph(str(v), ParagraphStyle("v", parent=E["kpi_val"], textColor=ROJO if r and v else AZUL))
               for _, v, r in kpis]]
    t = Table(celdas, colWidths=[ancho / len(kpis)] * len(kpis))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, BORDE), ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _chip(alerta: str) -> Paragraph:
    return Paragraph(f'<font color="{COLOR_ALERTA.get(alerta, GRIS).hexval()}"><b>{escape(alerta)}</b></font>',
                     E["celda"])


DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def agenda(titulo_mes: str, dias: list, kpis: list, alcance: str, generado: str) -> bytes:
    """PDF de la Agenda Despacho de un mes: indicadores y eventos día por día."""
    buf = io.BytesIO()
    doc = _documento(buf, f"Agenda Despacho · {titulo_mes}")
    ancho = doc.width
    h = [Paragraph(escape(f"BOLIVIA EN EL MUNDO · AGENDA DESPACHO · {titulo_mes.upper()}"), E["titulo"]),
         Paragraph(escape(f"{alcance} · {generado}"), E["sub"]), _kpis(kpis, ancho)]
    cab = ("Evento", "Código", "Unidad", "Tarea / recordatorio", "Responsable", "Estado", "Agenda", "Alerta")
    proporciones = (0.09, 0.08, 0.07, 0.34, 0.15, 0.11, 0.07, 0.09)
    if not dias:
        h.append(Spacer(1, 10))
        h.append(Paragraph("No hay fechas límite ni recordatorios en este mes.", E["celda"]))
    for fecha, evs in dias:
        filas = [[_p(c, "celda_cab") for c in cab]]
        for e in evs:
            t = e["info"].t
            texto = t.asunto if e["tipo"] == "limite" else f"{e['texto']}  (tarea: {t.asunto})"
            resp = ""
            if t.responsable:
                persona = t.responsable.persona
                resp = t.responsable.nombre + (f" ({persona})" if persona else "")
            filas.append([
                _p("Fecha límite" if e["tipo"] == "limite" else ("Recordatorio (hecho)" if e["hecho"] else "Recordatorio")),
                _p(t.codigo), _p(t.unidad.sigla), _p(texto), _p(resp or "Sin asignar"),
                _p(t.estado.valor), _p(e["estado_agenda"]), _chip(e["alerta"]),
            ])
        titulo = f"{DIAS[fecha.weekday()]} {formato_fecha(fecha)} · {len(evs)} evento(s)"
        h.append(KeepTogether([Paragraph(escape(titulo), E["h2"]),
                               _tabla(filas, [ancho * p for p in proporciones])]))
    h.append(Spacer(1, 6))
    h.append(Paragraph("Fechas límite de tareas abiertas y recordatorios (subtareas con fecha). "
                       "Estado de agenda: Pendiente, En gestión, Bloqueada (observado / devuelto) o Concluida.",
                       E["pie"]))
    pie = f"Agenda Despacho · {titulo_mes} · {generado}"
    doc.build(h, onFirstPage=lambda c, d: _pie(c, d, pie), onLaterPages=lambda c, d: _pie(c, d, pie))
    return buf.getvalue()


def _leyenda(pares, x, y, ancho) -> Legend:
    """Leyenda debajo del gráfico, en hasta 3 columnas."""
    ley = Legend()
    ley.x, ley.y = x, y
    ley.alignment = "left"
    ley.columnMaximum = max(1, -(-len(pares) // 3))
    ley.deltax = ancho / 3
    ley.deltay = 9
    ley.dx = ley.dy = 6
    ley.fontName, ley.fontSize = "Helvetica", 7
    ley.colorNamePairs = pares
    return ley


def _fuentes(g) -> None:
    for eje in (g.categoryAxis, g.valueAxis):
        eje.labels.fontName = "Helvetica"
        eje.labels.fontSize = 7


def _barras_unidad(barras, ancho) -> Drawing:
    alto = 175
    dib = Drawing(ancho, alto)
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 25, 40, ancho - 30, alto - 45
    g.data = [s["valores"] for s in barras["series"]] or [[0]]
    g.categoryAxis.categoryNames = barras["etiquetas"]
    g.categoryAxis.labels.fontSize = 7
    g.categoryAxis.style = "stacked"
    g.valueAxis.valueMin = 0
    g.valueAxis.labels.fontSize = 7
    maximo = max([sum(v) for v in zip(*g.data)] or [0])
    g.valueAxis.valueMax = max(4, maximo)
    g.valueAxis.valueStep = max(1, round(g.valueAxis.valueMax / 4))
    for k, s in enumerate(barras["series"]):
        g.bars[k].fillColor = colors.HexColor(s["color"])
        g.bars[k].strokeColor = None
    _fuentes(g)
    dib.add(g)
    dib.add(_leyenda([(colors.HexColor(s["color"]), s["alerta"]) for s in barras["series"]], 25, 22, ancho - 30))
    return dib


def _lineas_mes(mensual, ancho) -> Drawing:
    alto = 150
    dib = Drawing(ancho, alto)
    g = HorizontalLineChart()
    g.x, g.y, g.width, g.height = 25, 32, ancho - 30, alto - 37
    g.data = [mensual["creadas"], mensual["concluidas"]]
    g.categoryAxis.categoryNames = mensual["etiquetas"]
    g.categoryAxis.labels.fontSize = 7
    g.valueAxis.valueMin = 0
    g.valueAxis.valueMax = max(4, max(mensual["creadas"] + mensual["concluidas"] or [0]))
    g.valueAxis.valueStep = max(1, round(g.valueAxis.valueMax / 4))
    g.valueAxis.labels.fontSize = 7
    for k, color in enumerate(("#2E4A7D", "#3B9A63")):
        g.lines[k].strokeColor = colors.HexColor(color)
        g.lines[k].strokeWidth = 1.6
    _fuentes(g)
    dib.add(g)
    dib.add(_leyenda([(colors.HexColor("#2E4A7D"), "Creadas"), (colors.HexColor("#3B9A63"), "Concluidas")],
                     25, 12, ancho - 30))
    return dib


def _embudo(embudo, ancho) -> Drawing:
    alto = 30 + 18 * max(1, len(embudo))
    dib = Drawing(ancho, alto)
    if not embudo:
        dib.add(String(0, alto / 2, "Sin tareas abiertas.", fontName="Helvetica", fontSize=8))
        return dib
    g = HorizontalBarChart()
    g.x, g.y, g.width, g.height = 175, 15, ancho - 185, alto - 25
    g.data = [[x["valor"] for x in reversed(embudo)]]
    g.categoryAxis.categoryNames = [x["estado"][:40] for x in reversed(embudo)]
    g.categoryAxis.labels.fontSize = 7
    g.categoryAxis.labels.boxAnchor = "e"
    g.valueAxis.valueMin = 0
    g.valueAxis.valueMax = max(4, max(g.data[0]))
    g.valueAxis.valueStep = max(1, round(g.valueAxis.valueMax / 4))
    g.valueAxis.labels.fontSize = 7
    g.bars[0].fillColor = colors.HexColor("#2E4A7D")
    g.bars[0].strokeColor = None
    _fuentes(g)
    dib.add(g)
    return dib


def graficos(datos: dict, por_unidad: bool, proximos: list, alcance: str, generado: str) -> bytes:
    """PDF del tablero gráfico: los mismos bloques de la pantalla, dibujados con reportlab."""
    buf = io.BytesIO()
    doc = _documento(buf, "Tablero · Seguimiento MRE")
    ancho = doc.width
    mitad = (ancho - 8 * mm) / 2
    kpis = [(k["titulo"], k["valor"], k["alerta"]) for k in datos["tarjetas"]]
    h = [Paragraph("BOLIVIA EN EL MUNDO · TABLERO DE SEGUIMIENTO MRE", E["titulo"]),
         Paragraph(escape(f"{alcance} · {generado}"), E["sub"]), _kpis(kpis, ancho)]

    var = datos["tarjetas"][-1].get("variacion")
    if var is not None:
        h.append(Paragraph(escape(f"Concluidas este mes: {'+' if var > 0 else ''}{var} % frente al mes anterior."),
                           E["sub"]))

    c = datos["cumplimiento"]
    if c["pct"] is None:
        texto_c = "Aún no hay tareas concluidas con fecha límite."
    else:
        estado = "cumple" if c["pct"] >= c["meta"] else "no alcanza"
        texto_c = (f"{c['pct']} % de {c['base']} tareas concluidas con fecha límite se cerraron a tiempo "
                   f"(meta {c['meta']} %: {estado}).")

    if por_unidad:
        bloque_izq = [Paragraph("Pendientes por unidad, por alerta", E["h2"]), _barras_unidad(datos["barras"], mitad)]
    else:
        filas = [[_p(x, "celda_cab") for x in ("Código", "Tarea / asunto", "Límite", "Alerta")]]
        filas += [[_p(i.t.codigo), _p(i.t.asunto), _p(formato_fecha(i.t.fecha_limite)), _chip(i.alerta)]
                  for i in proximos] or [[_p("Sin fechas límite pendientes."), _p(""), _p(""), _p("")]]
        bloque_izq = [Paragraph("Próximos vencimientos", E["h2"]),
                      _tabla(filas, [mitad * 0.17, mitad * 0.53, mitad * 0.15, mitad * 0.15])]
    bloque_der = [Paragraph("Cumplimiento de plazos", E["h2"]), Paragraph(escape(texto_c), E["celda"])]
    if por_unidad and datos["anillos"]:
        filas = [[_p("Unidad", "celda_cab"), _p("A tiempo", "celda_cab"), _p("Base", "celda_cab")]]
        filas += [[_p(a["sigla"]), _p("—" if a["pct"] is None else f"{a['pct']} %", "num"), _p(a["base"], "num")]
                  for a in datos["anillos"]]
        bloque_der += [Spacer(1, 4), _tabla(filas, [mitad * 0.5, mitad * 0.25, mitad * 0.25])]
    filas = [[_p("Instancia del MRE", "celda_cab"), _p("Pendientes", "celda_cab")]]
    filas += [[_p(x["nombre"]), _p(x["valor"], "num")] for x in datos["instancias"]] or \
        [[_p("Sin gestiones pendientes con el MRE."), _p("")]]
    bloque_der += [Paragraph("Instancias del MRE con más pendientes", E["h2"]),
                   _tabla(filas, [mitad * 0.8, mitad * 0.2])]

    def lado_a_lado(izq, der):
        t = Table([[izq, der]], colWidths=[mitad + 4 * mm, mitad + 4 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm)]))
        return t

    h.append(lado_a_lado(bloque_izq, bloque_der))
    h.append(lado_a_lado(
        [Paragraph("Creadas contra concluidas (12 meses)", E["h2"]), _lineas_mes(datos["mensual"], mitad)],
        [Paragraph("Embudo de estados (tareas abiertas)", E["h2"]), _embudo(datos["embudo"], mitad)],
    ))
    pie = f"Tablero · {generado}"
    doc.build(h, onFirstPage=lambda cv, d: _pie(cv, d, pie), onLaterPages=lambda cv, d: _pie(cv, d, pie))
    return buf.getvalue()


# ------------------------------------------------------------------ conversión con LibreOffice
def ruta_soffice() -> str | None:
    """Ruta del ejecutable de LibreOffice, o None si no está instalado."""
    configurada = current_app.config.get("SOFFICE_PATH") or "soffice"
    if Path(configurada).is_file():
        return configurada
    return shutil.which(configurada)


def libreoffice_disponible() -> bool:
    return ruta_soffice() is not None


def convertir_a_pdf(datos: bytes, extension: str) -> bytes:
    """Convierte un .docx/.xlsx a PDF con LibreOffice headless, con tiempo límite.

    Trabaja en una carpeta temporal dentro de storage/generados/ que se borra siempre al terminar.
    """
    soffice = ruta_soffice()
    if not soffice:
        raise ErrorNegocio("LibreOffice no está instalado en el servidor: no se puede generar PDF. "
                           "Descargue el documento en su formato original.")
    carpeta = current_app.config["STORAGE_DIR"] / "generados" / uuid.uuid4().hex
    carpeta.mkdir(parents=True)
    try:
        entrada = carpeta / f"documento.{extension}"
        entrada.write_bytes(datos)
        perfil = (carpeta / "perfil").resolve().as_uri()  # perfil propio: permite conversiones simultáneas
        try:
            subprocess.run(
                [soffice, f"-env:UserInstallation={perfil}", "--headless", "--norestore", "--nologo",
                 "--convert-to", "pdf", "--outdir", str(carpeta), str(entrada)],
                check=True, capture_output=True, timeout=current_app.config["SOFFICE_TIMEOUT"],
            )
        except subprocess.TimeoutExpired as e:
            raise ErrorNegocio("La conversión a PDF tardó demasiado. Intente de nuevo o descargue el original.") from e
        except (subprocess.CalledProcessError, OSError) as e:
            current_app.logger.error("Fallo LibreOffice: %s", getattr(e, "stderr", e))
            raise ErrorNegocio("No se pudo convertir el documento a PDF.") from e
        salida = carpeta / "documento.pdf"
        if not salida.is_file():
            raise ErrorNegocio("No se pudo convertir el documento a PDF.")
        return salida.read_bytes()
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
