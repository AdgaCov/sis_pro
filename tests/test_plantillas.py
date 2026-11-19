"""Etapa 5: plantillas Word/Excel con marcadores, validación, generación y PDF."""
import io
import subprocess
from datetime import timedelta

import docx
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.extensions import db
from app.models import Auditoria, Catalogo, Plantilla
from app.services import ErrorNegocio, pdf
from app.services import plantillas as srv
from app.utils.fechas import hoy_local
from tests.conftest import unidad


# ------------------------------------------------------------------ archivos de prueba
def word(*parrafos, tabla_tareas=False) -> bytes:
    d = docx.Document()
    for p in parrafos:
        d.add_paragraph(p)
    if tabla_tareas:
        t = d.add_table(rows=3, cols=2)
        t.cell(0, 0).text = "{%tr for t in tareas %}"
        t.cell(1, 0).text = "{{ t.codigo }}"
        t.cell(1, 1).text = "{{ t.asunto }}"
        t.cell(2, 0).text = "{%tr endfor %}"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def excel() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Listado de {{ unidad.nombre }}"
    ws["A2"], ws["B2"], ws["C2"] = "Código", "Asunto", "Alerta"
    ws["A3"], ws["B3"], ws["C3"] = "{{ t.codigo }}", "{{ t.asunto }}", "{{ t.alerta }}"
    ws["A3"].font = Font(bold=True, color="FF0000")
    ws["A5"], ws["B5"] = "Total", "{{ resumen.total }}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def texto_word(datos: bytes) -> str:
    d = docx.Document(io.BytesIO(datos))
    partes = [p.text for p in d.paragraphs]
    for t in d.tables:
        partes += [c.text for fila in t.rows for c in fila.cells]
    return "\n".join(partes)


def subir(c, datos, nombre, alcance="tarea", titulo="Ficha"):
    return c.post("/admin/plantillas/nueva", data={
        "nombre": titulo, "alcance": alcance, "archivo": (io.BytesIO(datos), nombre),
    }, content_type="multipart/form-data")


@pytest.fixture
def admin(como):
    c, u = como("admin")
    return c


# ------------------------------------------------------------------ validación de marcadores
def test_marcadores_conocidos_y_desconocidos():
    usados = srv.marcadores_en("{{ tarea.codigo }} {{ tarea.inventado }} {% for t in tareas %}{{ t.asunto|upper }}"
                               "{% for s in t.subtareas %}{{ s.texto }}{{ loop.index }}{% endfor %}{% endfor %}")
    assert {"tarea.codigo", "tarea.inventado", "tareas", "tarea.asunto", "tarea.subtareas",
            "subtarea.texto"} <= usados
    assert [u for u in usados if not srv.es_conocido(u)] == ["tarea.inventado"]


def test_sintaxis_invalida():
    with pytest.raises(ErrorNegocio, match="sintaxis"):
        srv.marcadores_en("{% for t in tareas %}{{ t.codigo }}")


def test_subir_word_lista_desconocidos(admin, app):
    r = subir(admin, word("{{ tarea.codigo }} {{ tarea.no_existe }}"), "ficha.docx")
    assert r.status_code == 302
    p = Plantilla.query.one()
    assert p.formato == "docx" and p.marcadores_desconocidos == ["tarea.no_existe"]
    assert srv.ruta_archivo(p).is_file()
    assert "tarea.no_existe" in admin.get("/admin/plantillas").get_data(as_text=True)


def test_subir_excel_valida_filas_t(admin):
    subir(admin, excel(), "listado.xlsx", alcance="listado")
    p = Plantilla.query.one()
    assert p.formato == "xlsx" and p.marcadores_desconocidos == []


@pytest.mark.parametrize("datos,nombre,mensaje", [
    (b"no es zip", "malo.docx", "Word"),
    (b"no es zip", "malo.xlsx", "Excel"),
    (b"%PDF", "algo.pdf", ".docx"),
])
def test_rechaza_archivos_invalidos(admin, datos, nombre, mensaje):
    r = subir(admin, datos, nombre)
    assert r.status_code == 200 and mensaje in r.get_data(as_text=True)
    assert Plantilla.query.count() == 0


def test_rechaza_sintaxis_rota_al_subir(admin):
    r = subir(admin, word("{% if tarea.codigo %}sin cerrar"), "rota.docx")
    assert "sintaxis" in r.get_data(as_text=True) and Plantilla.query.count() == 0


def test_reemplazar_archivo_borra_el_anterior(admin):
    subir(admin, word("{{ tarea.codigo }}"), "v1.docx")
    p = Plantilla.query.one()
    viejo = srv.ruta_archivo(p)
    admin.post(f"/admin/plantillas/{p.id}/editar", data={
        "nombre": "Ficha v2", "alcance": "tarea", "archivo": (io.BytesIO(excel()), "v2.xlsx"),
    }, content_type="multipart/form-data")
    db.session.refresh(p)
    assert not viejo.exists() and p.formato == "xlsx" and p.nombre == "Ficha v2"


def test_eliminar_borra_archivo(admin):
    subir(admin, word("{{ tarea.codigo }}"), "v1.docx")
    p = Plantilla.query.one()
    ruta = srv.ruta_archivo(p)
    admin.post(f"/admin/plantillas/{p.id}/eliminar")
    assert Plantilla.query.count() == 0 and not ruta.exists()


@pytest.mark.parametrize("rol,sigla", [("supervisor", None), ("unidad", "UAF"), ("invitado", None)])
def test_solo_admin_administra_plantillas(como, rol, sigla):
    c, _ = como(rol, sigla)
    for ruta in ["/admin/plantillas", "/admin/plantillas/nueva", "/admin/plantillas/marcadores"]:
        assert c.get(ruta).status_code == 403
    assert subir(c, word("x"), "x.docx").status_code == 403


# ------------------------------------------------------------------ generación
@pytest.fixture
def con_tareas(hacer_tarea):
    hoy = hoy_local()
    a, b = hacer_tarea("UAF"), hacer_tarea("UAF")
    a.asunto, a.fecha_limite = "Pasajes & viáticos <FITUR>", hoy - timedelta(days=1)
    b.asunto = "Segunda tarea"
    hacer_tarea("UPT").asunto = "Tarea ajena"
    db.session.commit()
    return a, b


def test_probar_con_datos_de_ejemplo(admin):
    subir(admin, word("Hola {{ tarea.codigo }} · {{ generado.por }}", tabla_tareas=True), "f.docx")
    p = Plantilla.query.one()
    r = admin.get(f"/admin/plantillas/{p.id}/probar")
    assert r.status_code == 200
    texto = texto_word(r.data)
    assert "Hola UAF-001" in texto and "UAF-003" in texto and "Tarea de ejemplo 2" in texto


def test_ficha_de_tarea_en_word(como, admin, con_tareas):
    subir(admin, word("{{ tarea.codigo }} — {{ tarea.asunto }} — {{ tarea.alerta }} — {{ unidad.nombre }}"),
          "ficha.docx")
    p = Plantilla.query.one()
    a, _ = con_tareas
    c, _ = como("unidad", "UAF")
    r = c.get(f"/documentos/{p.id}/tarea/{a.id}")
    assert r.status_code == 200 and "Ficha_UAF-001.docx" in r.headers["Content-Disposition"]
    texto = texto_word(r.data)
    # los caracteres especiales se escapan bien en el XML del Word
    assert "UAF-001 — Pasajes & viáticos <FITUR> — VENCIDO — UAF - Unidad Administrativa Financiera" in texto
    assert Auditoria.query.filter_by(accion="generar_documento").count() == 1


def test_error_de_ejecucion_en_plantilla_no_rompe(como, admin, con_tareas):
    """Un marcador que falla al evaluarse (sumar texto y número) avisa al usuario en vez de dar error 500."""
    subir(admin, word("{{ tarea.codigo + 1 }}"), "ficha.docx")
    p = Plantilla.query.one()
    a, _ = con_tareas
    c, _ = como("unidad", "UAF")
    r = c.get(f"/documentos/{p.id}/tarea/{a.id}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/tareas/{a.id}")
    assert "revise sus marcadores" in c.get(r.headers["Location"]).get_data(as_text=True)


def test_ficha_de_tarea_ajena_no(como, admin, con_tareas):
    subir(admin, word("{{ tarea.codigo }}"), "ficha.docx")
    p = Plantilla.query.one()
    ajena = db.session.query(type(con_tareas[0])).filter_by(codigo="UPT-001").one()
    c, _ = como("unidad", "UAF")
    assert c.get(f"/documentos/{p.id}/tarea/{ajena.id}").status_code == 404


def test_listado_en_excel_repite_filas(como, admin, con_tareas):
    subir(admin, excel(), "listado.xlsx", alcance="listado")
    p = Plantilla.query.one()
    c, _ = como("unidad", "UAF")
    r = c.get(f"/documentos/{p.id}/listado")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.data)).active
    assert ws["A1"].value == "Listado de UAF - Unidad Administrativa Financiera"
    filas = [(ws.cell(f, 1).value, ws.cell(f, 3).value) for f in (3, 4)]
    assert filas == [("UAF-001", "VENCIDO"), ("UAF-002", "SIN FECHA")]  # ordenadas por severidad
    assert ws["A4"].font.bold and ws["A4"].font.color.rgb.endswith("FF0000")  # conserva formato
    assert ws["A6"].value == "Total" and ws["B6"].value == 2  # la fila de totales se desplazó y es número
    assert "Tarea ajena" not in str([c.value for fila in ws.iter_rows() for c in fila])


def test_listado_respeta_filtros(admin, con_tareas):
    subir(admin, excel(), "listado.xlsx", alcance="listado")
    p = Plantilla.query.one()
    r = admin.get(f"/documentos/{p.id}/listado?alerta=VENCIDO")
    ws = load_workbook(io.BytesIO(r.data)).active
    assert ws["A3"].value == "UAF-001" and ws["A4"].value is None and ws["B5"].value == 1


def test_listado_sin_tareas_deja_fila_vacia(admin):
    subir(admin, excel(), "listado.xlsx", alcance="listado")
    p = Plantilla.query.one()
    ws = load_workbook(io.BytesIO(admin.get(f"/documentos/{p.id}/listado").data)).active
    assert ws["A3"].value is None and ws["B5"].value == 0


def test_informe_solo_criticas(admin, con_tareas):
    subir(admin, word("Críticas: {{ resumen.total }}", tabla_tareas=True), "inf.docx", alcance="informe")
    p = Plantilla.query.one()
    texto = texto_word(admin.get(f"/documentos/{p.id}/informe").data)
    assert "Críticas: 1" in texto and "UAF-001" in texto and "UAF-002" not in texto


def test_alcance_e_inactiva(admin, con_tareas):
    subir(admin, word("{{ tarea.codigo }}"), "ficha.docx")
    p = Plantilla.query.one()
    assert admin.get(f"/documentos/{p.id}/listado").status_code == 404  # alcance distinto
    p.activa = False
    db.session.commit()
    assert admin.get(f"/documentos/{p.id}/tarea/{con_tareas[0].id}").status_code == 404


def test_invitado_no_genera_documentos(como, admin, con_tareas):
    subir(admin, word("{{ tarea.codigo }}"), "ficha.docx")
    p = Plantilla.query.one()
    c, _ = como("invitado", permisos={"todas_unidades": True})
    assert c.get(f"/documentos/{p.id}/tarea/{con_tareas[0].id}").status_code == 403
    assert c.get(f"/documentos/{p.id}/listado").status_code == 403


def test_sandbox_bloquea_codigo_peligroso(admin, con_tareas):
    subir(admin, word("{{ ''.__class__.__mro__[1].__subclasses__() }}"), "malo.docx")
    p = Plantilla.query.one()
    r = admin.get(f"/documentos/{p.id}/tarea/{con_tareas[0].id}")
    assert r.status_code == 302  # vuelve al detalle con un mensaje, sin ejecutar nada
    assert "No se pudo llenar" in admin.get(r.headers["Location"]).get_data(as_text=True)


def test_menu_generar_documento(como, admin, con_tareas):
    subir(admin, word("{{ tarea.codigo }}"), "ficha.docx")
    subir(admin, excel(), "listado.xlsx", alcance="listado", titulo="Listado")
    c, _ = como("unidad", "UAF")
    assert "Generar documento" in c.get(f"/tareas/{con_tareas[0].id}").get_data(as_text=True)
    assert "/documentos/" in c.get("/tareas").get_data(as_text=True)


# ------------------------------------------------------------------ PDF con LibreOffice
def test_pdf_sin_libreoffice(admin, con_tareas, app):
    app.config["SOFFICE_PATH"] = "no-existe-soffice"
    subir(admin, word("{{ tarea.codigo }}"), "ficha.docx")
    p = Plantilla.query.one()
    r = admin.get(f"/documentos/{p.id}/tarea/{con_tareas[0].id}?formato=pdf")
    assert r.status_code == 302
    assert "LibreOffice no está instalado" in admin.get(r.headers["Location"]).get_data(as_text=True)


def test_pdf_con_libreoffice_simulado(admin, con_tareas, app, monkeypatch, tmp_path):
    falso = tmp_path / "soffice.exe"
    falso.write_text("")
    app.config["SOFFICE_PATH"] = str(falso)
    llamadas = []

    def run(cmd, **kw):
        llamadas.append((cmd, kw))
        salida = cmd[cmd.index("--outdir") + 1]
        (__import__("pathlib").Path(salida) / "documento.pdf").write_bytes(b"%PDF-1.4 falso")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    subir(admin, word("{{ tarea.codigo }}"), "ficha.docx")
    p = Plantilla.query.one()
    r = admin.get(f"/documentos/{p.id}/tarea/{con_tareas[0].id}?formato=pdf")
    assert r.status_code == 200 and r.data == b"%PDF-1.4 falso" and r.mimetype == "application/pdf"
    cmd, kw = llamadas[0]
    assert "--headless" in cmd and kw["timeout"] == app.config["SOFFICE_TIMEOUT"]
    assert list((app.config["STORAGE_DIR"] / "generados").iterdir()) == []  # temporales borrados


def test_pdf_tiempo_limite(admin, con_tareas, app, monkeypatch, tmp_path):
    falso = tmp_path / "soffice.exe"
    falso.write_text("")
    app.config["SOFFICE_PATH"] = str(falso)

    def run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(pdf.subprocess, "run", run)
    with pytest.raises(ErrorNegocio, match="tardó demasiado"):
        pdf.convertir_a_pdf(word("x"), "docx")
    assert list((app.config["STORAGE_DIR"] / "generados").iterdir()) == []


# ------------------------------------------------------------------ resumen, agenda y gráficos
def word_con_tabla(parrafos, lista, celdas) -> bytes:
    """Word con párrafos y una tabla cuya fila se repite por cada elemento de `lista`."""
    d = docx.Document()
    for p in parrafos:
        d.add_paragraph(p)
    t = d.add_table(rows=3, cols=len(celdas))
    var = celdas[0].split("{{ ")[1].split(".")[0]
    t.cell(0, 0).text = f"{{%tr for {var} in {lista} %}}"
    for k, c in enumerate(celdas):
        t.cell(1, k).text = c
    t.cell(2, 0).text = "{%tr endfor %}"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def excel_filas(*filas) -> bytes:
    wb = Workbook()
    ws = wb.active
    for fila in filas:
        ws.append(list(fila))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def imagenes_en(datos: bytes) -> list[str]:
    import zipfile
    return [n for n in zipfile.ZipFile(io.BytesIO(datos)).namelist() if n.startswith("word/media/")]


def test_resumen_ejecutivo_en_word(admin, con_tareas):
    subir(admin, word_con_tabla(["Gestiones: {{ indicadores.total_mre }} · vencidas {{ indicadores.vencidas }}"],
                                "por_unidad", ["{{ u.sigla }}", "{{ u.pendientes }}", "{{ u.vencidas }}"]),
          "resumen.docx", alcance="resumen")
    p = Plantilla.query.one()
    assert p.marcadores_desconocidos == []
    r = admin.get(f"/documentos/{p.id}/resumen")
    assert r.status_code == 200 and r.headers["Content-Disposition"].endswith('.docx')
    texto = texto_word(r.data)
    assert "Gestiones: 3 · vencidas 1" in texto
    assert "UAF" in texto and "UPT" in texto and "SISTEMAS" in texto
    # el menú aparece en la vista
    assert f"/documentos/{p.id}/resumen" in admin.get("/tablero/resumen").get_data(as_text=True)


def test_resumen_en_excel_repite_unidades_e_instancias(como, admin, con_tareas):
    a, _ = con_tareas
    a.instancia_id = Catalogo.query.filter_by(tipo="instancia").first().id
    db.session.commit()
    subir(admin, excel_filas(("{{ unidad.nombre }}",), ("{{ u.sigla }}", "{{ u.total }}"), ("Instancias",),
                             ("{{ i.nombre }}", "{{ i.pendientes }}"), ("{{ t.codigo }}", "{{ t.asunto }}")),
          "resumen.xlsx", alcance="resumen")
    p = Plantilla.query.one()
    assert p.marcadores_desconocidos == []
    c, _ = como("unidad", "UAF")
    ws = load_workbook(io.BytesIO(c.get(f"/documentos/{p.id}/resumen").data)).active
    valores = [[x.value for x in fila] for fila in ws.iter_rows()]
    assert valores[0][0] == "UAF - Unidad Administrativa Financiera"
    assert valores[1][:2] == ["UAF", 2]  # la unidad solo ve su unidad; total como número
    assert valores[2][0] == "Instancias"
    instancia = Catalogo.query.get(a.instancia_id).valor
    assert sorted(v[0] for v in valores[3:5]) == sorted([instancia, "Sin instancia"])  # como en la vista
    assert [v[0] for v in valores[5:7]] == ["UAF-001", "UAF-002"]
    assert "UPT" not in str(valores)


def test_agenda_en_excel_con_eventos_del_mes(admin, con_tareas):
    a, _ = con_tareas
    subir(admin, excel_filas(("Agenda {{ mes.nombre }}", "{{ indicadores.fechas_limite }}"),
                             ("{{ e.fecha }}", "{{ e.codigo }}", "{{ e.tipo }}", "{{ e.alerta }}")),
          "agenda.xlsx", alcance="agenda")
    p = Plantilla.query.one()
    assert p.marcadores_desconocidos == []
    mes = f"{a.fecha_limite:%Y-%m}"
    r = admin.get(f"/documentos/{p.id}/agenda?mes={mes}")
    assert r.status_code == 200 and f"_{a.fecha_limite:%Y_%m}.xlsx" in r.headers["Content-Disposition"]
    ws = load_workbook(io.BytesIO(r.data)).active
    assert ws["A1"].value.startswith("Agenda ") and ws["B1"].value == 1
    assert [ws["B2"].value, ws["C2"].value, ws["D2"].value] == ["UAF-001", "Fecha límite", "VENCIDO"]


def test_graficos_en_word_con_imagenes(admin, con_tareas):
    subir(admin, word_con_tabla(
        ["Pendientes {{ indicadores.pendientes }} · cumplimiento {{ cumplimiento.porcentaje }}",
         "{{ imagen.barras }}", "{{ imagen.cumplimiento }}", "{{ imagen.mensual }}", "{{ imagen.embudo }}"],
        "embudo", ["{{ f.estado }}", "{{ f.tareas }}"]), "tablero.docx", alcance="graficos")
    p = Plantilla.query.one()
    assert p.marcadores_desconocidos == []
    r = admin.get(f"/documentos/{p.id}/graficos")
    assert r.status_code == 200
    assert "Pendientes 3" in texto_word(r.data) and "Pendiente" in texto_word(r.data)
    assert len(imagenes_en(r.data)) == 4  # los cuatro gráficos como imágenes
    for ruta in ("/", "/tablero/graficos"):
        assert f"/documentos/{p.id}/graficos" in admin.get(ruta).get_data(as_text=True)


def test_graficos_en_excel_por_unidad_y_mensual(admin, con_tareas):
    subir(admin, excel_filas(("{{ u.sigla }}", "{{ u.vencido }}", "{{ u.pendientes }}"),
                             ("{{ m.mes }}", "{{ m.creadas }}")), "tablero.xlsx", alcance="graficos")
    p = Plantilla.query.one()
    ws = load_workbook(io.BytesIO(admin.get(f"/documentos/{p.id}/graficos").data)).active
    filas = [[x.value for x in fila] for fila in ws.iter_rows()]
    assert filas[0] == ["DGE-STAF", 0, 0] and ["UAF", 1, 2] in filas and ["UPT", 0, 1] in filas
    assert len(filas) == 6 + 12  # 6 unidades y 12 meses


@pytest.mark.parametrize("alcance,ruta", [("resumen", "resumen"), ("agenda", "agenda"), ("graficos", "graficos")])
def test_invitado_no_genera_documentos_del_tablero(como, admin, alcance, ruta):
    subir(admin, word("{{ unidad.nombre }}"), "x.docx", alcance=alcance)
    p = Plantilla.query.one()
    c, _ = como("invitado", permisos={"todas_unidades": True})
    assert c.get(f"/documentos/{p.id}/{ruta}").status_code == 403
    vista = {"resumen": "/tablero/resumen", "agenda": "/agenda", "graficos": "/tablero/graficos"}[alcance]
    assert f"/documentos/{p.id}/" not in c.get(vista).get_data(as_text=True)  # tampoco ve el menú


def test_alcance_distinto_da_404(admin):
    subir(admin, word("{{ unidad.nombre }}"), "x.docx", alcance="agenda")
    p = Plantilla.query.one()
    assert admin.get(f"/documentos/{p.id}/resumen").status_code == 404


@pytest.mark.parametrize("alcance", ["resumen", "agenda", "graficos"])
def test_probar_alcances_del_tablero(admin, alcance):
    subir(admin, word("{{ mes.nombre }} {{ indicadores.pendientes }} {% for u in por_unidad %}{{ u.sigla }} {% endfor %}",
                      "{{ imagen.barras }}"), "x.docx", alcance=alcance)
    p = Plantilla.query.one()
    r = admin.get(f"/admin/plantillas/{p.id}/probar")
    assert r.status_code == 200
    assert "Noviembre 2026 9 UAF UPT" in texto_word(r.data) and len(imagenes_en(r.data)) == 1


def test_imagenes_png_aun_sin_datos():
    from app.services import imagenes

    vacio = {"barras": {"etiquetas": [], "unidades": [], "series": []},
             "cumplimiento": {"pct": None, "base": 0, "meta": 80},
             "mensual": {"etiquetas": ["ene 26"], "creadas": [0], "concluidas": [0]}, "embudo": []}
    for png in imagenes.todas(vacio).values():
        assert png.startswith(b"\x89PNG")


def test_pagina_de_marcadores_agrupada(admin):
    html = admin.get("/admin/plantillas/marcadores").get_data(as_text=True)
    for texto in ("Resumen ejecutivo", "Agenda Despacho", "Tablero con gráficos", "fila_unidad.sigla",
                  "imagen.barras", "evento.codigo"):
        assert texto in html
