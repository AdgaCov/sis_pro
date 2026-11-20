"""Etapa 6: Agenda Despacho y tablero de gráficos, con sus PDF, para todos los roles (invitado: solo MRE)."""
import json
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import Catalogo, Subtarea
from app.services import agenda as ag
from app.services import alertas as al
from app.services import graficos
from app.utils.fechas import hoy_local
from tests.conftest import unidad

HOY = date(2026, 11, 18)


def cat(tipo, valor):
    return Catalogo.query.filter_by(tipo=tipo, valor=valor).one()


@pytest.fixture
def datos(hacer_tarea):
    """UAF: una gestión MRE que vence pronto con un recordatorio, y una interna. UPT: una gestión vencida."""
    hoy = hoy_local()
    mre = hacer_tarea("UAF")
    mre.asunto, mre.fecha_solicitud, mre.fecha_limite = "Gestión MRE de UAF", hoy - timedelta(days=3), hoy + timedelta(days=2)
    mre.subtareas.append(Subtarea(texto="Llamar a Cancillería", fecha=hoy + timedelta(days=1), hecho=False, orden=0))
    interna = hacer_tarea("UAF")
    interna.tipo_id = cat("tipo", "Tarea interna").id
    interna.asunto, interna.fecha_limite = "Tarea interna reservada", hoy + timedelta(days=2)
    upt = hacer_tarea("UPT")
    upt.asunto, upt.fecha_limite = "Gestión de UPT", hoy - timedelta(days=1)
    db.session.commit()
    return mre, interna, upt


# ------------------------------------------------------------------ servicio de agenda
def test_estado_agenda():
    assert ag.estado_agenda("Concluido") == "Concluida"
    assert ag.estado_agenda("Pendiente") == "Pendiente"
    assert ag.estado_agenda("Observado / Devuelto") == "Bloqueada"
    assert ag.estado_agenda("Remitido a DGE") == "En gestión"


def test_leer_mes_y_vecinos():
    assert ag.leer_mes("2026-02", HOY) == date(2026, 2, 1)
    assert ag.leer_mes("basura", HOY) == date(2026, 11, 1)
    # años absurdos: el mes actual (antes 0001-01 o 9999-12 rompían la navegación con error 500)
    assert ag.leer_mes("0001-01", HOY) == ag.leer_mes("9999-12", HOY) == date(2026, 11, 1)
    assert ag.mes_vecino(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert ag.mes_vecino(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_eventos_y_calendario(hacer_tarea):
    t = hacer_tarea("UAF")
    t.fecha_limite = date(2026, 11, 20)
    t.subtareas.append(Subtarea(texto="paso vencido", fecha=date(2026, 11, 10), hecho=False, orden=0))
    t.subtareas.append(Subtarea(texto="paso hecho", fecha=date(2026, 11, 12), hecho=True, orden=1))
    cerrada = hacer_tarea("UAF")
    cerrada.estado_id, cerrada.fecha_limite = cat("estado", "Concluido").id, date(2026, 11, 20)
    db.session.commit()
    evs = ag.eventos(al.calcular([t, cerrada], HOY), date(2026, 11, 1), date(2026, 11, 30), HOY)
    assert [(e["fecha"].day, e["tipo"], e["alerta"]) for e in evs] == [
        (10, "recordatorio", al.VENCIDO), (12, "recordatorio", al.CONCLUIDO), (20, "limite", al.POR_VENCER)]
    semanas = ag.calendario(date(2026, 11, 1), evs, HOY)
    assert all(len(s) == 7 for s in semanas) and semanas[0][0]["fecha"].weekday() == 0
    dias = {d["fecha"]: d for s in semanas for d in s}
    assert dias[date(2026, 11, 10)]["peor"] == "VENCIDO"
    assert dias[date(2026, 11, 12)]["peor"] is None  # solo un paso hecho
    assert dias[HOY]["hoy"]


# ------------------------------------------------------------------ vista y PDF de la agenda
@pytest.mark.parametrize("rol,sigla", [("admin", None), ("supervisor", None), ("unidad", "UAF")])
def test_agenda_para_usuarios(como, datos, rol, sigla):
    c, _ = como(rol, sigla)
    html = c.get("/agenda").get_data(as_text=True)
    assert "Gestión MRE de UAF" in html and "Llamar a Cancillería" in html
    assert "Tarea interna reservada" in html  # los usuarios internos ven también las internas
    assert ("Gestión de UPT" in html) == (rol != "unidad")


def test_invitado_ve_agenda_solo_mre_de_sus_unidades(como, datos):
    c, _ = como("invitado", unidades_invitado=["UAF"])
    html = c.get("/agenda").get_data(as_text=True)
    assert "Gestión MRE de UAF" in html
    assert "Tarea interna reservada" not in html and "Gestión de UPT" not in html
    assert "/tareas/" not in html  # sin enlaces al detalle


def test_agenda_navega_por_meses(como, datos):
    c, _ = como("admin")
    assert c.get("/agenda?mes=2027-01").status_code == 200
    assert "Enero 2027" in c.get("/agenda?mes=2027-01").get_data(as_text=True)
    for raro in ("0001-01", "9999-12", "1-1", "2026-13"):
        assert c.get(f"/agenda?mes={raro}").status_code == 200
        assert c.get(f"/agenda/agenda.pdf?mes={raro}").status_code == 302  # sin plantilla: vuelve a la vista


def test_agenda_muestra_tres_meses(como, hacer_tarea):
    """En pantalla: mes anterior, el elegido y el siguiente (también al cambiar de año)."""
    t = hacer_tarea("UAF")
    t.asunto, t.fecha_limite = "Vence en febrero", date(2027, 2, 10)
    db.session.commit()
    c, _ = como("admin")
    html = c.get("/agenda?mes=2027-01").get_data(as_text=True)
    assert html.count('class="col-xl-4"') == 3
    assert "Diciembre 2026" in html and "Enero 2027" in html and "Febrero 2027" in html
    assert "Vence en febrero" in html  # el evento del mes siguiente también se ve
    assert 'href="/agenda?mes=2026-12"' in html and 'href="/agenda?mes=2027-02"' in html  # meses vecinos enlazan


def test_mes_en_pantalla_no_repite_eventos_de_otros_meses(hacer_tarea):
    t = hacer_tarea("UAF")
    t.fecha_limite = date(2026, 12, 1)  # aparece como relleno al final de la grilla de noviembre
    db.session.commit()
    infos = al.calcular([t], HOY)
    evs = ag.eventos(infos, date(2026, 10, 1), date(2027, 1, 31), HOY)
    nov = ag.mes_en_pantalla(date(2026, 11, 1), evs, HOY, elegido=True)
    dic = ag.mes_en_pantalla(date(2026, 12, 1), evs, HOY)
    assert nov["eventos"] == 0 and not any(d["eventos"] for s in nov["semanas"] for d in s)
    assert dic["eventos"] == 1 and nov["elegido"] and not dic["elegido"]


def test_pdf_agenda(como, datos, poner_plantilla, pdf_como_texto):
    mre, interna, upt = datos
    poner_plantilla("agenda", "Agenda {{ mes.nombre }}", "{% for e in eventos %}[{{ e.codigo }} {{ e.texto }}]{% endfor %}")
    mes = f"{mre.fecha_limite:%Y-%m}"
    c, _ = como("invitado", unidades_invitado=["UAF", "UPT"])
    assert "/agenda/agenda.pdf" in c.get(f"/agenda?mes={mes}").get_data(as_text=True)
    r = c.get(f"/agenda/agenda.pdf?mes={mes}", follow_redirects=True)
    assert r.status_code == 200 and r.data.startswith(b"%PDF") and r.mimetype == "application/pdf"
    assert f"_{mre.fecha_limite:%Y_%m}.pdf" in r.headers["Content-Disposition"]
    assert b"UAF-001" in r.data and "Tarea interna reservada".encode() not in r.data


# ------------------------------------------------------------------ gráficos
def test_datos_graficos(hacer_tarea, app):
    hoy = HOY
    a_tiempo, tarde, abierta = hacer_tarea("UAF"), hacer_tarea("UAF"), hacer_tarea("UPT")
    concluido = cat("estado", "Concluido").id
    a_tiempo.estado_id, a_tiempo.fecha_limite, a_tiempo.fecha_conclusion = concluido, date(2026, 11, 10), date(2026, 11, 9)
    tarde.estado_id, tarde.fecha_limite, tarde.fecha_conclusion = concluido, date(2026, 10, 1), date(2026, 10, 5)
    abierta.fecha_limite = date(2026, 11, 1)
    for t in (a_tiempo, tarde, abierta):
        t.creado_en = datetime(2026, 10, 15, 12, 0)
    db.session.commit()
    unidades = [unidad("UAF"), unidad("UPT")]
    d = graficos.datos(al.calcular([a_tiempo, tarde, abierta], hoy), unidades, True, 80, hoy)
    tarjetas = {k["clave"]: k for k in d["tarjetas"]}
    assert tarjetas["pendientes"]["valor"] == 1 and tarjetas["vencidas"]["valor"] == 1
    assert tarjetas["concluidas_mes"]["valor"] == 1 and tarjetas["concluidas_mes"]["variacion"] == 0
    # las tarjetas enlazan a la lista filtrada
    sin_resp = Catalogo.query.filter_by(tipo="estado", valor="En instancia del MRE – Sin respuesta").one()
    assert tarjetas["pendientes"]["filtro"] == {}
    assert tarjetas["sin_respuesta"]["filtro"] == {"estado_id": sin_resp.id}
    assert d["cumplimiento"] == {"pct": 50, "base": 2, "meta": 80}
    vencidas = next(s for s in d["barras"]["series"] if s["alerta"] == al.VENCIDO)
    assert vencidas["valores"] == [0, 1]  # UAF, UPT
    assert d["mensual"]["creadas"][-2] == 3 and d["mensual"]["concluidas"][-1] == 1
    assert [a["pct"] for a in d["anillos"]] == [50, None]
    assert d["embudo"] == [{"id": cat("estado", "Pendiente").id, "estado": "Pendiente", "valor": 1}]
    json.dumps(d)  # todo es serializable para el navegador


@pytest.mark.parametrize("rol,sigla", [("admin", None), ("supervisor", None), ("unidad", "UAF")])
def test_vista_graficos(como, datos, rol, sigla):
    c, _ = como(rol, sigla)
    html = c.get("/tablero/graficos").get_data(as_text=True)
    assert 'id="datosGraficos"' in html and "chart.js@4.4.1" in html
    # la unidad ve «Próximos vencimientos» en lugar de barras por unidad y anillos
    assert ("Próximos vencimientos" in html) == (rol == "unidad")
    assert ('id="gUnidades"' in html) == (rol != "unidad")


def test_invitado_graficos_solo_mre(como, datos):
    c, _ = como("invitado", unidades_invitado=["UAF"])
    html = c.get("/tablero/graficos").get_data(as_text=True)
    datos_js = json.loads(html.split('id="datosGraficos">')[1].split("</script>")[0])
    assert {k["clave"]: k["valor"] for k in datos_js["tarjetas"]}["pendientes"] == 1  # sin la interna
    assert 'data-tareas=""' in html  # no navega a tareas


def test_pdf_graficos(como, datos, poner_plantilla, pdf_como_texto):
    poner_plantilla("graficos", "TABLERO {{ indicadores.pendientes }}", "{% for t in tareas %}[{{ t.codigo }}]{% endfor %}")
    for rol, sigla, kw in [("admin", None, {}), ("unidad", "UAF", {}), ("invitado", None, {"unidades_invitado": ["UAF"]})]:
        c, _ = como(rol, sigla, **kw)
        r = c.get("/tablero/graficos.pdf", follow_redirects=True)
        assert r.status_code == 200 and r.data.startswith(b"%PDF"), rol
        assert b"TABLERO" in r.data
        if rol != "admin":
            assert b"UPT-001" not in r.data, rol  # solo sus unidades
        if rol == "invitado":
            assert b"UAF-002" not in r.data  # la interna no sale al invitado


# ------------------------------------------------------------------ permisos del invitado
def test_invitado_menu_y_vistas(como):
    c, _ = como("invitado", permisos={"todas_unidades": True})
    html = c.get("/tablero/resumen").get_data(as_text=True)
    assert "/agenda" in html and "/tablero/graficos" in html
    for ruta in ["/tablero/alertas", "/tablero/informe", "/tablero/cronograma", "/tareas", "/responsables"]:
        assert c.get(ruta).status_code == 403, ruta


def test_sin_sesion(client):
    for ruta in ["/agenda", "/agenda/agenda.pdf", "/tablero/graficos", "/tablero/graficos.pdf"]:
        assert client.get(ruta).status_code == 302
