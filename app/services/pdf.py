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
