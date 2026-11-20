"""Etapa 4: el invitado solo ve el resumen ejecutivo (y agenda y gráficos) y los descarga en PDF con la plantilla
que sube el admin, con las unidades que el admin configure."""
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Auditoria, Catalogo, Usuario
from app.utils.fechas import hoy_local
from tests.conftest import unidad


@pytest.fixture
def gestiones(hacer_tarea):
    hoy = hoy_local()
    interna = Catalogo.query.filter_by(tipo="tipo", valor="Tarea interna").one()
    uaf, upt = hacer_tarea("UAF"), hacer_tarea("UPT")
    uaf.fecha_limite = upt.fecha_limite = hoy - timedelta(days=1)
    privada = hacer_tarea("UPT")
    privada.tipo_id = interna.id
    privada.asunto = "Tarea interna reservada"
    db.session.commit()
    return uaf, upt, privada


# ------------------------------------------------------------------ PDF (la plantilla que sube el admin)
DETALLE = "{% for t in tareas %}[{{ t.codigo }} {{ t.asunto }}]{% endfor %}"


@pytest.fixture
def plantilla_resumen(poner_plantilla, pdf_como_texto):
    return poner_plantilla("resumen", "Resumen {{ unidad.nombre }}", DETALLE)


def descargar(c, url):
    return c.get(url, follow_redirects=True)


def test_pdf_del_resumen(como, gestiones, plantilla_resumen):
    c, _ = como("admin")
    r = descargar(c, "/tablero/resumen.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF") and "attachment" in r.headers["Content-Disposition"]
    assert r.headers["Content-Disposition"].startswith("attachment; filename=Plantilla_resumen_")
    assert b"UAF-001" in r.data and b"UPT-001" in r.data
    assert b"Tarea interna reservada" not in r.data  # el resumen no incluye internas
    assert Auditoria.query.filter_by(accion="descargar_pdf").count() == 1


def test_pdf_respeta_filtros(como, gestiones, plantilla_resumen):
    c, _ = como("admin")
    r = descargar(c, f"/tablero/resumen.pdf?unidad_id={unidad('UAF').id}")
    # el detalle solo trae UAF (los cuadros por unidad siguen mostrando todas)
    assert b"UAF-001" in r.data and b"UPT-001" not in r.data


def test_invitado_descarga_pdf_solo_con_sus_unidades(como, gestiones, plantilla_resumen):
    c, _ = como("invitado", unidades_invitado=["UPT"])
    r = descargar(c, "/tablero/resumen.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert b"UPT-001" in r.data and b"UAF-001" not in r.data
    assert b"Tarea interna reservada" not in r.data
    # aunque pida otra unidad por filtro, no la obtiene
    r = descargar(c, f"/tablero/resumen.pdf?unidad_id={unidad('UAF').id}")
    assert b"UAF-001" not in r.data


def test_invitado_sin_unidades_descarga_pdf_vacio(como, gestiones, plantilla_resumen):
    c, _ = como("invitado")
    r = descargar(c, "/tablero/resumen.pdf")
    assert r.status_code == 200 and b"UAF-001" not in r.data and b"UPT-001" not in r.data


def test_sin_plantilla_no_hay_pdf(como, gestiones):
    c, _ = como("invitado", permisos={"todas_unidades": True})
    assert "/tablero/resumen.pdf" not in c.get("/tablero/resumen").get_data(as_text=True)  # no hay botón
    r = c.get("/tablero/resumen.pdf")
    assert r.status_code == 302 and r.headers["Location"].endswith("/tablero/resumen")
    assert "Todavía no hay una plantilla" in c.get(r.headers["Location"]).get_data(as_text=True)


def test_pdf_requiere_sesion(client):
    r = client.get("/tablero/resumen.pdf")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_invitado_ve_boton_pdf(como, plantilla_resumen):
    c, _ = como("invitado", permisos={"todas_unidades": True})
    html = c.get("/tablero/resumen").get_data(as_text=True)
    assert "/tablero/resumen.pdf" in html
    # menú solo con el resumen
    assert "/tablero/alertas" not in html and 'href="/tareas"' not in html and "/responsables" not in html


def test_invitado_no_llega_a_documentos_que_no_ve(como, poner_plantilla, hacer_tarea):
    t = hacer_tarea("UAF")
    ficha, listado, informe = (poner_plantilla(a, "{{ unidad.nombre }}") for a in ("tarea", "listado", "informe"))
    c, _ = como("invitado", permisos={"todas_unidades": True})
    assert c.get(f"/documentos/{ficha.id}/tarea/{t.id}?formato=pdf").status_code == 403
    assert c.get(f"/documentos/{listado.id}/listado?formato=pdf").status_code == 403
    assert c.get(f"/documentos/{informe.id}/informe?formato=pdf").status_code == 403
    assert c.get("/tablero/informe.pdf").status_code == 403


# ------------------------------------------------------------------ configuración por el admin
def test_admin_configura_unidades_del_invitado(como, hacer_usuario):
    inv = hacer_usuario("invitado")
    c, _ = como("admin")
    assert c.get("/admin/invitados").status_code == 200
    assert c.get(f"/admin/invitados/{inv.id}").status_code == 200
    r = c.post(f"/admin/invitados/{inv.id}", data={"unidades": [unidad("UAF").id, unidad("UEP").id]})
    assert r.status_code == 302
    db.session.refresh(inv)
    assert sorted(u.sigla for u in inv.permiso_invitado.unidades) == ["UAF", "UEP"]
    assert not inv.permiso_invitado.todas_unidades
    c.post(f"/admin/invitados/{inv.id}", data={"todas_unidades": "y", "unidades": [unidad("UAF").id]})
    db.session.refresh(inv)
    assert inv.permiso_invitado.todas_unidades and inv.permiso_invitado.unidades == []
    assert Auditoria.query.filter_by(accion="configurar_invitado").count() == 2


def test_solo_invitados_se_configuran(como, hacer_usuario):
    otro = hacer_usuario("supervisor")
    c, _ = como("admin")
    assert c.get(f"/admin/invitados/{otro.id}").status_code == 404


@pytest.mark.parametrize("rol,sigla", [("supervisor", None), ("unidad", "UAF"), ("invitado", None)])
def test_solo_admin_configura_invitados(como, hacer_usuario, rol, sigla):
    inv = hacer_usuario("invitado")
    c, _ = como(rol, sigla)
    assert c.get("/admin/invitados").status_code == 403
    assert c.post(f"/admin/invitados/{inv.id}", data={"todas_unidades": "y"}).status_code == 403
    db.session.refresh(inv)
    assert not inv.permiso_invitado.todas_unidades


def test_crear_invitado_lleva_a_configurarlo(como):
    c, _ = como("admin")
    r = c.post("/admin/usuarios/nuevo", data={
        "nombre_usuario": "visita", "nombre_completo": "Visita MRE", "rol": "invitado", "unidad_id": "0",
        "clave": "Visita2026", "confirmar": "Visita2026",
    })
    inv = Usuario.query.filter_by(nombre_usuario="visita").one()
    assert r.headers["Location"].endswith(f"/admin/invitados/{inv.id}")
