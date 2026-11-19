"""Etapa 3: alertas calculadas, resumen ejecutivo, informe crítico, cronograma y filtros."""
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import Catalogo, Subtarea
from app.services import alertas as al
from app.services import resumen
from app.utils.fechas import hoy_local

HOY = date(2026, 6, 15)


def cat(tipo, valor):
    return Catalogo.query.filter_by(tipo=tipo, valor=valor).one()


@pytest.fixture
def tarea(hacer_tarea):
    """Crea una tarea de UAF con los campos indicados."""

    def _hacer(sigla="UAF", **campos):
        t = hacer_tarea(sigla)
        for k, v in campos.items():
            if k in ("estado", "prioridad", "tipo", "instancia"):
                setattr(t, k, cat(k, v))
            else:
                setattr(t, k, v)
        db.session.commit()
        return t

    return _hacer


def alerta(t, hoy=HOY):
    return al.info(t, hoy).alerta


# ------------------------------------------------------------------ reglas de alerta (en orden)
def test_concluido_gana_a_todo(tarea):
    t = tarea(estado="Concluido", fecha_limite=HOY - timedelta(days=30), prioridad="Alta")
    assert alerta(t) == al.CONCLUIDO


def test_vencido(tarea):
    assert alerta(tarea(fecha_limite=HOY - timedelta(days=1))) == al.VENCIDO
    assert alerta(tarea(fecha_limite=HOY)) == al.POR_VENCER  # hoy todavía no vence


def test_critico_prioridad_alta_mas_de_15_dias(tarea):
    t = tarea(prioridad="Alta", fecha_solicitud=HOY - timedelta(days=16), fecha_limite=HOY + timedelta(days=2))
    assert alerta(t) == al.CRITICO  # gana a POR VENCER
    t15 = tarea(prioridad="Alta", fecha_solicitud=HOY - timedelta(days=15))
    assert alerta(t15) == al.SEGUIMIENTO
    media = tarea(prioridad="Media", fecha_solicitud=HOY - timedelta(days=30))
    assert alerta(media) == al.SEGUIMIENTO


def test_por_vencer(tarea):
    assert alerta(tarea(fecha_solicitud=HOY, fecha_limite=HOY + timedelta(days=3))) == al.POR_VENCER
    assert alerta(tarea(fecha_solicitud=HOY, fecha_limite=HOY + timedelta(days=4))) == al.EN_CURSO


def test_sin_fecha_seguimiento_en_curso(tarea):
    assert alerta(tarea()) == al.SIN_FECHA
    assert alerta(tarea(fecha_solicitud=HOY - timedelta(days=8))) == al.SEGUIMIENTO
    assert alerta(tarea(fecha_solicitud=HOY - timedelta(days=7))) == al.EN_CURSO


def test_umbrales_vienen_de_config(app, tarea):
    t = tarea(fecha_solicitud=HOY, fecha_limite=HOY + timedelta(days=5))
    assert alerta(t) == al.EN_CURSO
    app.config["DIAS_POR_VENCER"] = 5
    assert alerta(t) == al.POR_VENCER


# ------------------------------------------------------------------ señales y tarea crítica
def test_senales(tarea, hacer_usuario):
    otra = tarea()
    t = tarea(fecha_solicitud=HOY - timedelta(days=2), habilita_a_id=otra.id,
              actualizado_en=datetime(2026, 6, 1, 15, 0))
    t.subtareas.append(Subtarea(texto="paso", fecha=HOY - timedelta(days=1), hecho=False, orden=0))
    t.subtareas.append(Subtarea(texto="hecho", fecha=HOY - timedelta(days=1), hecho=True, orden=1))
    db.session.commit()
    infos = {i.t.id: i for i in al.calcular([t, otra], HOY)}
    i = infos[t.id]
    assert i.sin_actualizar and i.bloquea and i.sin_responsable and i.sin_fecha_limite
    assert [s.texto for s in i.subtareas_vencidas] == ["paso"]
    assert infos[otra.id].bloqueada_por == [t.codigo]


def test_concluida_sin_respaldo(tarea):
    assert al.info(tarea(estado="Concluido"), HOY).sin_respaldo
    assert not al.info(tarea(estado="Concluido", medio_verificacion="Nota 12/2026"), HOY).sin_respaldo


@pytest.mark.parametrize("campos,critica", [
    ({"fecha_limite": HOY - timedelta(days=1)}, True),                                       # vencida
    ({"prioridad": "Alta", "fecha_solicitud": HOY - timedelta(days=20)}, True),              # CRÍTICO
    ({"nivel_riesgo": "Alto"}, True),                                                        # riesgo alto
    ({"prioridad": "Alta", "fecha_solicitud": HOY, "fecha_limite": HOY + timedelta(days=2)}, True),
    ({"prioridad": "Media", "fecha_solicitud": HOY, "fecha_limite": HOY + timedelta(days=2)}, False),
    ({"estado": "Concluido", "nivel_riesgo": "Alto"}, False),                                # cerrada
])
def test_tarea_critica(tarea, campos, critica):
    i = al.info(tarea(**campos), HOY)
    assert i.critica is critica
    assert i.sin_solucion is critica  # ninguna tiene línea de solución


def test_orden_por_severidad(tarea):
    en_curso = tarea(fecha_solicitud=HOY)
    vencida = tarea(fecha_limite=HOY - timedelta(days=3))
    por_vencer = tarea(fecha_solicitud=HOY, fecha_limite=HOY + timedelta(days=1))
    orden = [i.t.id for i in al.ordenar(al.calcular([en_curso, vencida, por_vencer], HOY))]
    assert orden == [vencida.id, por_vencer.id, en_curso.id]


# ------------------------------------------------------------------ filtros
def test_filtrar_por_alerta_texto_y_concluidas(tarea, hacer_usuario):
    hoy = hoy_local()
    vencida = tarea(fecha_limite=hoy - timedelta(days=2), asunto="Pasajes para la feria")
    tarea(estado="Concluido", asunto="Pasajes ya listos")
    admin = hacer_usuario("admin")
    infos = resumen.cargar(admin)
    assert [i.t.id for i in resumen.filtrar(infos, {"alerta": al.VENCIDO})] == [vencida.id]
    assert len(resumen.filtrar(infos, {"texto": "PASAJES"})) == 1
    assert len(resumen.filtrar(infos, {"texto": "pasajes", "ver_concluidas": True})) == 2
    assert len(resumen.filtrar(infos, {"alerta": al.CONCLUIDO})) == 1


def test_listado_filtra_por_alerta(como, tarea):
    hoy = hoy_local()
    tarea(fecha_limite=hoy - timedelta(days=2))
    tarea(fecha_solicitud=hoy)
    c, _ = como("unidad", "UAF")
    html = c.get("/tareas?alerta=VENCIDO").get_data(as_text=True)
    assert "UAF-001" in html and "UAF-002" not in html


def test_resumen_ejecutivo_excluye_internas(tarea, hacer_usuario):
    tarea(tipo="Tarea interna")
    tarea(tipo="Solicitud al MRE", estado="En instancia del MRE – Sin respuesta")
    admin = hacer_usuario("admin")
    datos = resumen.resumen_ejecutivo(resumen.cargar(admin), resumen.permisos.unidades_visibles(admin))
    kpis = {k: v for k, v, _ in datos["kpis"]}
    assert kpis["Total gestiones MRE"] == 1 and kpis["Sin respuesta del MRE"] == 1
    uaf = next(r for r in datos["por_unidad"] if r["unidad"].sigla == "UAF")
    assert uaf["total"] == 1


def test_cronograma_posiciones(tarea, hacer_usuario):
    t = tarea(fecha_solicitud=HOY - timedelta(days=10), fecha_limite=HOY + timedelta(days=10))
    sin = tarea()
    admin = hacer_usuario("admin")
    infos = al.calcular([t, sin], HOY)
    datos = resumen.cronograma(infos, [t.unidad], agrupar=False, hoy=HOY)
    fila = datos["grupos"][0]["filas"][0]
    assert 0 <= fila["izq"] < datos["hoy"] < fila["izq"] + fila["ancho"] <= 100
    assert fila["hito"] is not None and fila["hito"] > datos["hoy"]
    assert [i.t.id for i in datos["sin_fechas"]] == [sin.id]
    assert datos["meses"]


# ------------------------------------------------------------------ permisos de las vistas
VISTAS = {"resumen": "/tablero/resumen", "alertas": "/tablero/alertas", "informe": "/tablero/informe",
          "cronograma": "/tablero/cronograma"}


def _datos_de_prueba(tarea):
    hoy = hoy_local()
    tarea("UAF", fecha_solicitud=hoy - timedelta(days=5), fecha_limite=hoy - timedelta(days=1), asunto="Asunto UAF visible")
    tarea("UPT", fecha_solicitud=hoy - timedelta(days=5), fecha_limite=hoy - timedelta(days=1), asunto="Asunto UPT oculto")


@pytest.mark.parametrize("ruta", VISTAS.values())
def test_unidad_solo_ve_su_unidad_en_el_tablero(como, tarea, ruta):
    _datos_de_prueba(tarea)
    c, _ = como("unidad", "UAF")
    html = c.get(ruta).get_data(as_text=True)
    assert "UAF-001" in html
    assert "UPT-001" not in html and "Asunto UPT oculto" not in html


@pytest.mark.parametrize("rol", ["admin", "supervisor"])
@pytest.mark.parametrize("ruta", VISTAS.values())
def test_admin_y_supervisor_ven_todo_en_el_tablero(como, tarea, rol, ruta):
    _datos_de_prueba(tarea)
    c, _ = como(rol)
    html = c.get(ruta).get_data(as_text=True)
    assert "UAF-001" in html and "UPT-001" in html


@pytest.mark.parametrize("ruta", ["/tablero/alertas", "/tablero/informe", "/tablero/cronograma"])
def test_invitado_no_ve_otras_vistas(como, ruta):
    c, _ = como("invitado", permisos={"todas_unidades": True})
    assert c.get(ruta).status_code == 403


def test_invitado_ve_resumen_solo_de_sus_unidades(como, tarea):
    _datos_de_prueba(tarea)
    c, _ = como("invitado", unidades_invitado=["UPT"])
    html = c.get("/tablero/resumen").get_data(as_text=True)
    assert "UPT-001" in html and "UAF-001" not in html and "Asunto UAF" not in html
    assert "/tareas/" not in html  # sin enlaces al detalle
    assert c.get("/").headers["Location"].endswith("/tablero/resumen")


def test_inicio_muestra_indicadores_y_enlaces(como, tarea):
    _datos_de_prueba(tarea)
    c, _ = como("unidad", "UAF")
    html = c.get("/").get_data(as_text=True)
    assert "Vencidas" in html and "/tablero/alertas" in html
    # el inicio es el dashboard: trae los gráficos (unidad: próximos vencimientos en vez de barras)
    assert 'id="datosGraficos"' in html and "Cumplimiento de plazos" in html
    assert "Próximos vencimientos" in html and "chart.umd.min.js" in html


def test_inicio_admin_tiene_graficos_por_unidad_y_filtro(como, tarea):
    _datos_de_prueba(tarea)
    c, _ = como("admin")
    html = c.get("/").get_data(as_text=True)
    assert 'id="gUnidades"' in html and "Cumplimiento por unidad" in html and 'action="/"' in html
    # filtrando por una unidad, deja de comparar unidades
    from tests.conftest import unidad
    uaf = unidad("UAF").id
    html = c.get(f"/?unidad_id={uaf}").get_data(as_text=True)
    assert 'id="gUnidades"' not in html and "Próximos vencimientos" in html


def test_detalle_muestra_alerta_y_senales(como, tarea):
    t = tarea(fecha_limite=hoy_local() - timedelta(days=1))
    c, _ = como("unidad", "UAF")
    html = c.get(f"/tareas/{t.id}").get_data(as_text=True)
    assert "VENCIDO" in html and "Sin responsable" in html


# ------------------------------------------------------------------ PDF del informe crítico
@pytest.fixture
def pdf_legible(monkeypatch):
    from reportlab import rl_config

    monkeypatch.setattr(rl_config, "pageCompression", 0)


def test_informe_critico_se_descarga_en_pdf(como, tarea, pdf_legible):
    from app.models import Auditoria

    _datos_de_prueba(tarea)  # una vencida en UAF y otra en UPT
    c, _ = como("admin")
    assert "/tablero/informe.pdf" in c.get("/tablero/informe").get_data(as_text=True)
    r = c.get("/tablero/informe.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert "Informe_Critico_" in r.headers["Content-Disposition"]
    assert b"UAF-001" in r.data and b"UPT-001" in r.data and b"Sin definir" in r.data
    assert Auditoria.query.filter_by(accion="descargar_pdf", entidad="informe").count() == 1


def test_informe_pdf_respeta_unidad_y_permisos(como, tarea, pdf_legible):
    _datos_de_prueba(tarea)
    c, _ = como("unidad", "UAF")
    r = c.get("/tablero/informe.pdf")
    assert b"UAF-001" in r.data and b"UPT-001" not in r.data  # la unidad no ve otra unidad
    inv, _ = como("invitado", permisos={"todas_unidades": True})
    assert inv.get("/tablero/informe.pdf").status_code == 403  # el invitado no ve el informe
