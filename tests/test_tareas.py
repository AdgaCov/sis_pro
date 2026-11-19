"""Etapa 2: tareas, responsables, subtareas, dependencias, adjuntos y papelera."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Auditoria, Cargo, Catalogo, Tarea
from app.services import ErrorNegocio
from app.services import tareas as srv
from app.utils.fechas import hoy_local
from tests.conftest import unidad


def cat(tipo, valor):
    return Catalogo.query.filter_by(tipo=tipo, valor=valor).one().id


def cargo(sigla, nombre="Apoyo"):
    return Cargo.query.filter_by(unidad_id=unidad(sigla).id, nombre=nombre).one()


def datos(**extra):
    d = {"tipo_id": cat("tipo", "Solicitud al MRE"), "estado_id": cat("estado", "Pendiente"),
         "asunto": "Solicitar autorización de viaje"}
    d.update(extra)
    return d


def form(**extra):
    """Datos como los manda el navegador."""
    return {k: ("" if v is None else str(v)) for k, v in datos(**extra).items()}


# ------------------------------------------------------------------ alta y códigos
def test_unidad_crea_tareas_con_codigo_correlativo(como):
    c, _ = como("unidad", "UAF")
    r = c.post("/tareas/nueva", data=form())
    assert r.status_code == 302
    c.post("/tareas/nueva", data=form(asunto="Otra"))
    assert [t.codigo for t in Tarea.query.order_by(Tarea.id)] == ["UAF-001", "UAF-002"]
    t = Tarea.query.first()
    assert t.creado_por_id and t.actualizado_por_id and t.unidad.sigla == "UAF"


def test_unidad_no_elige_otra_unidad_al_crear(como):
    c, _ = como("unidad", "UAF")
    c.post("/tareas/nueva", data=form(unidad_id=unidad("UPT").id))
    assert Tarea.query.one().codigo == "UAF-001"


def test_admin_crea_en_cualquier_unidad(como):
    c, _ = como("admin")
    c.post("/tareas/nueva", data=form(unidad_id=unidad("UPT").id))
    assert Tarea.query.one().codigo == "UPT-001"


def test_asunto_obligatorio(como):
    c, _ = como("unidad", "UAF")
    r = c.post("/tareas/nueva", data=form(asunto="  "))
    assert r.status_code == 200 and Tarea.query.count() == 0


def test_concluido_pone_fecha_de_hoy(hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    t = srv.guardar_tarea(u, datos(estado_id=cat("estado", "Concluido")))
    assert t.fecha_conclusion == hoy_local()
    t2 = srv.guardar_tarea(u, datos(estado_id=cat("estado", "Concluido"), fecha_conclusion=date(2026, 1, 5)))
    assert t2.fecha_conclusion == date(2026, 1, 5)


def test_fecha_limite_no_anterior_a_solicitud(hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    with pytest.raises(ErrorNegocio, match="anterior"):
        srv.guardar_tarea(u, datos(fecha_solicitud=date(2026, 5, 10), fecha_limite=date(2026, 5, 1)))


def test_catalogo_inactivo_no_se_puede_elegir(hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    otro = Catalogo.query.filter_by(tipo="estado", valor="Otro").one()
    otro.activo = False
    db.session.commit()
    with pytest.raises(ErrorNegocio):
        srv.guardar_tarea(u, datos(estado_id=otro.id))


# ------------------------------------------------------------------ permisos
def test_unidad_no_ve_ni_edita_tareas_de_otra(como, hacer_tarea):
    ajena = hacer_tarea("UPT")
    c, _ = como("unidad", "UAF")
    assert c.get(f"/tareas/{ajena.id}").status_code == 404
    assert c.get(f"/tareas/{ajena.id}/editar").status_code == 404
    assert c.post(f"/tareas/{ajena.id}/editar", data=form()).status_code == 404
    assert c.post(f"/tareas/{ajena.id}/eliminar").status_code == 404
    assert b"UPT-001" not in c.get("/tareas?ver_concluidas=y").data
    assert db.session.get(Tarea, ajena.id) is not None


def test_listado_de_unidad_solo_muestra_lo_suyo(como, hacer_tarea):
    hacer_tarea("UAF")
    hacer_tarea("UPT")
    c, _ = como("unidad", "UAF")
    html = c.get("/tareas").data
    assert b"UAF-001" in html and b"UPT-001" not in html


def test_supervisor_edita_cualquier_unidad(como, hacer_tarea):
    t = hacer_tarea("UEP")
    c, _ = como("supervisor")
    r = c.post(f"/tareas/{t.id}/editar", data=form(asunto="Editado por DGE", unidad_id=t.unidad_id))
    assert r.status_code == 302
    assert db.session.get(Tarea, t.id).asunto == "Editado por DGE"


@pytest.mark.parametrize("ruta", ["/tareas/nueva", "/tareas/{id}/editar", "/tareas/{id}/eliminar",
                                  "/tareas/{id}/adjuntos", "/tareas/{id}/subtareas/1",
                                  "/tareas/{id}/adjuntos/1/quitar"])
def test_invitado_no_escribe_en_tareas(como, hacer_tarea, ruta):
    t = hacer_tarea("UAF")
    c, _ = como("invitado", permisos={"todas_unidades": True})
    assert c.post(ruta.format(id=t.id), data=form()).status_code == 403
    assert Tarea.query.count() == 1


def test_invitado_no_entra_a_tareas(como, hacer_tarea):
    t = hacer_tarea("UAF")
    c, _ = como("invitado", permisos={"todas_unidades": True})
    for ruta in ["/tareas", f"/tareas/{t.id}", f"/tareas/{t.id}/editar", "/tareas/nueva"]:
        assert c.get(ruta).status_code == 403, ruta


def test_unidad_sin_unidad_no_crea(como):
    c, _ = como("unidad")
    assert c.get("/tareas/nueva").status_code == 403


# ------------------------------------------------------------------ reasignación
def test_unidad_no_puede_reasignar(hacer_usuario, hacer_tarea):
    t = hacer_tarea("UAF")
    u = hacer_usuario("unidad", "UAF")
    srv.guardar_tarea(u, datos(unidad_id=unidad("UPT").id), t)
    assert t.codigo == "UAF-001"


def test_reasignar_da_codigo_nuevo_y_conserva_referencias(hacer_usuario, hacer_tarea):
    admin = hacer_usuario("admin")
    origen = hacer_tarea("UAF")
    dependiente = hacer_tarea("UAF")
    dependiente.habilita_a_id = origen.id
    db.session.commit()
    hacer_tarea("UPT")  # UPT-001 ya existe
    srv.guardar_tarea(admin, datos(unidad_id=unidad("UPT").id), origen)
    assert origen.codigo == "UPT-002" and origen.unidad.sigla == "UPT"
    assert db.session.get(Tarea, dependiente.id).habilita_a.codigo == "UPT-002"
    reg = Auditoria.query.filter_by(accion="reasignar_tarea").one()
    assert reg.detalle == {"de": "UAF-001", "a": "UPT-002"}


# ------------------------------------------------------------------ responsables en la tarea
def test_unidad_no_asigna_cargo_de_otra_unidad(hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    with pytest.raises(ErrorNegocio, match="otra unidad"):
        srv.guardar_tarea(u, datos(responsable_id=cargo("UPT").id))
    t = srv.guardar_tarea(u, datos(responsable_id=cargo("UAF").id))
    assert t.responsable.nombre == "Apoyo"


def test_admin_asigna_cargo_de_otra_unidad(hacer_usuario):
    admin = hacer_usuario("admin")
    t = srv.guardar_tarea(admin, datos(unidad_id=unidad("UAF").id, responsable_id=cargo("UPT").id))
    assert t.responsable.unidad.sigla == "UPT"


# ------------------------------------------------------------------ dependencias
def test_habilita_solo_misma_unidad_para_unidad(hacer_usuario, hacer_tarea):
    ajena = hacer_tarea("UPT")
    u = hacer_usuario("unidad", "UAF")
    with pytest.raises(ErrorNegocio):
        srv.guardar_tarea(u, datos(habilita_a_id=ajena.id))
    propia = hacer_tarea("UAF")
    t = srv.guardar_tarea(u, datos(habilita_a_id=propia.id))
    assert t.habilita_a_id == propia.id


def test_tarea_no_se_habilita_a_si_misma(hacer_usuario, hacer_tarea):
    t = hacer_tarea("UAF")
    u = hacer_usuario("unidad", "UAF")
    with pytest.raises(ErrorNegocio, match="sí misma"):
        srv.guardar_tarea(u, datos(habilita_a_id=t.id), t)


# ------------------------------------------------------------------ subtareas
def test_subtareas_desde_formulario(como):
    c, _ = como("unidad", "UAF")
    data = form()
    data.update({"subtareas-0-texto": "Paso uno", "subtareas-0-fecha": "2026-12-01", "subtareas-0-hecho": "y",
                 "subtareas-5-texto": "Paso dos", "subtareas-7-texto": "   "})
    c.post("/tareas/nueva", data=data)
    t = Tarea.query.one()
    assert [(s.texto, s.hecho) for s in t.subtareas] == [("Paso uno", True), ("Paso dos", False)]
    assert t.subtareas[0].fecha == date(2026, 12, 1)
    # al editar sin subtareas, se borran
    c.post(f"/tareas/{t.id}/editar", data=form())
    db.session.expire_all()
    assert db.session.get(Tarea, t.id).subtareas == []


def test_maximo_40_subtareas(hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    with pytest.raises(ErrorNegocio, match="40"):
        srv.guardar_tarea(u, datos(subtareas=[{"texto": f"p{i}"} for i in range(41)]))


def test_marcar_subtarea(como):
    c, u = como("unidad", "UAF")
    t = srv.guardar_tarea(u, datos(subtareas=[{"texto": "Paso"}]))
    sid = t.subtareas[0].id
    c.post(f"/tareas/{t.id}/subtareas/{sid}", data={"hecho": "1"})
    db.session.expire_all()
    assert db.session.get(Tarea, t.id).subtareas[0].hecho
    reg = Auditoria.query.filter_by(accion="marcar_subtarea").one()
    assert reg.entidad_id == str(t.id) and reg.detalle["hecho"] is True


# ------------------------------------------------------------------ eliminar / papelera
def test_eliminar_copia_a_papelera_y_limpia_referencias(como, hacer_tarea):
    objetivo = hacer_tarea("UAF")
    dependiente = hacer_tarea("UAF")
    dependiente.habilita_a_id = objetivo.id
    db.session.commit()
    c, _ = como("unidad", "UAF")
    assert c.post(f"/tareas/{objetivo.id}/eliminar").status_code == 302
    assert db.session.get(Tarea, objetivo.id) is None
    assert db.session.get(Tarea, dependiente.id).habilita_a_id is None
    reg = Auditoria.query.filter_by(accion="eliminar_tarea").one()
    assert reg.detalle["codigo"] == "UAF-001" and reg.detalle["asunto"] == "Asunto de UAF"


def test_papelera_solo_admin(como):
    for rol, sigla in [("supervisor", None), ("unidad", "UAF")]:
        c, _ = como(rol, sigla)
        assert c.get("/tareas/papelera").status_code == 403
    c, _ = como("admin")
    assert c.get("/tareas/papelera").status_code == 200


def test_el_codigo_no_se_reutiliza_tras_eliminar(hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    t = srv.guardar_tarea(u, datos())
    srv.eliminar_tarea(u, t)
    assert srv.guardar_tarea(u, datos()).codigo == "UAF-002"


# ------------------------------------------------------------------ adjuntos
def subir(c, tarea, nombre="nota.pdf", contenido=b"%PDF-1.4 prueba"):
    return c.post(f"/tareas/{tarea.id}/adjuntos", data={"archivo": (io.BytesIO(contenido), nombre)},
                  content_type="multipart/form-data")


def test_subir_descargar_y_quitar_adjunto(como, hacer_tarea, app):
    t = hacer_tarea("UAF")
    c, _ = como("unidad", "UAF")
    assert subir(c, t).status_code == 302
    adj = db.session.get(Tarea, t.id).adjuntos[0]
    ruta = app.config["STORAGE_DIR"] / "respaldos" / adj.ruta_relativa
    assert ruta.is_file() and adj.ruta_relativa.startswith(f"UAF/{t.id}/")
    r = c.get(f"/tareas/{t.id}/adjuntos/{adj.id}")
    assert r.status_code == 200 and r.data == b"%PDF-1.4 prueba"
    assert "nota.pdf" in r.headers["Content-Disposition"]
    r.close()
    c.post(f"/tareas/{t.id}/adjuntos/{adj.id}/quitar")
    assert not ruta.exists() and db.session.get(Tarea, t.id).adjuntos == []


def test_adjunto_rechaza_extension_y_tamano(como, hacer_tarea, app):
    t = hacer_tarea("UAF")
    c, _ = como("unidad", "UAF")
    subir(c, t, "virus.exe")
    app.config["MAX_MB_ADJUNTO"] = 0  # cualquier archivo supera 0 MB
    subir(c, t)
    assert db.session.get(Tarea, t.id).adjuntos == []


def test_adjunto_de_otra_unidad_no_se_descarga(como, hacer_tarea):
    t = hacer_tarea("UAF")
    c, _ = como("unidad", "UAF")
    subir(c, t)
    adj = db.session.get(Tarea, t.id).adjuntos[0]
    otro, _ = como("unidad", "UPT")
    assert otro.get(f"/tareas/{t.id}/adjuntos/{adj.id}").status_code == 404
    assert subir(otro, t).status_code == 404


def test_invitado_no_descarga_adjuntos(como, hacer_tarea):
    t = hacer_tarea("UAF")
    c, _ = como("unidad", "UAF")
    subir(c, t)
    adj = db.session.get(Tarea, t.id).adjuntos[0]
    inv, _ = como("invitado", permisos={"todas_unidades": True})
    assert inv.get(f"/tareas/{t.id}/adjuntos/{adj.id}").status_code == 403


# ------------------------------------------------------------------ pantallas
@pytest.mark.parametrize("rol,sigla", [("admin", None), ("supervisor", None), ("unidad", "UAF")])
def test_pantallas_se_muestran(como, rol, sigla):
    c, u = como(rol, sigla)
    t = srv.guardar_tarea(u, datos(unidad_id=unidad("UAF").id, responsable_id=cargo("UAF").id,
                                   subtareas=[{"texto": "Paso", "fecha": date(2026, 12, 1)}]))
    for ruta in ["/tareas", "/tareas/nueva", f"/tareas/{t.id}", f"/tareas/{t.id}/editar", "/responsables", "/"]:
        r = c.get(ruta)
        assert r.status_code == 200, ruta
    html = c.get(f"/tareas/{t.id}/editar").get_data(as_text=True)
    assert 'name="subtareas-0-texto"' in html and 'value="Paso"' in html
    assert ('name="unidad_id"' in html) == (rol != "unidad")


def test_texto_filtros_incluye_estado_prioridad_y_responsable(app, hacer_usuario):
    from flask_login import login_user

    from app.controllers.tareas import formulario_filtros, texto_filtros

    u = hacer_usuario("admin")
    args = {"estado_id": cat("estado", "Pendiente"), "prioridad_id": cat("prioridad", "Alta"),
            "responsable_id": cargo("UAF").id}
    with app.test_request_context("/tareas", query_string=args):
        login_user(u)
        texto = texto_filtros(formulario_filtros())
    assert "Estado: Pendiente" in texto and "Prioridad: Alta" in texto and "Responsable: UAF · Apoyo" in texto
