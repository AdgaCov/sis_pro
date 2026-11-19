"""Administración de catálogos."""
import pytest

from app.extensions import db
from app.models import Auditoria, Catalogo, Tarea
from app.services import ErrorNegocio
from app.services import catalogos as srv


def valor(tipo, v):
    return Catalogo.query.filter_by(tipo=tipo, valor=v).one()


@pytest.fixture
def admin(como):
    c, u = como("admin")
    return c, u


def test_pantalla_por_tipo(admin):
    c, _ = admin
    for tipo in ("estado", "tipo", "instancia", "prioridad", "area"):
        assert c.get(f"/admin/catalogos?tipo={tipo}").status_code == 200
    assert c.get("/admin/catalogos?tipo=otro").status_code == 404
    html = c.get("/admin/catalogos?tipo=estado").get_data(as_text=True)
    assert "Concluido" in html and "protegido" in html


def test_agregar_al_final_sin_duplicados(admin):
    c, _ = admin
    c.post("/admin/catalogos/estado/agregar", data={"valor": "  En  revisión legal "})
    nuevo = valor("estado", "En revisión legal")
    assert nuevo.orden == max(x.orden for x in srv.valores("estado")) and nuevo.activo
    c.post("/admin/catalogos/estado/agregar", data={"valor": "en revisión LEGAL"})
    assert Catalogo.query.filter(Catalogo.valor.ilike("en revisión legal")).count() == 1


def test_renombrar_se_refleja_en_tareas(admin, hacer_tarea):
    c, _ = admin
    t = hacer_tarea("UAF")  # estado Pendiente
    pendiente = valor("estado", "Pendiente")
    c.post(f"/admin/catalogos/{pendiente.id}/renombrar", data={"valor": "Por iniciar"})
    db.session.expire_all()
    assert db.session.get(Tarea, t.id).estado.valor == "Por iniciar"
    assert Auditoria.query.filter_by(accion="renombrar_catalogo").one().detalle == {"antes": "Pendiente",
                                                                                     "despues": "Por iniciar"}


@pytest.mark.parametrize("tipo,v", [("tipo", "Tarea interna"), ("estado", "Concluido"), ("prioridad", "Alta")])
def test_protegidos_no_se_tocan(app, hacer_usuario, tipo, v):
    admin = hacer_usuario("admin")
    c = valor(tipo, v)
    for accion in (lambda: srv.renombrar(admin, c, "Otro nombre"), lambda: srv.cambiar_estado(admin, c, False),
                   lambda: srv.eliminar(admin, c)):
        with pytest.raises(ErrorNegocio, match="protegido"):
            accion()
    db.session.expire_all()
    c = db.session.get(Catalogo, c.id)
    assert c.valor == v and c.activo


def test_desactivar_lo_quita_del_formulario_pero_la_tarea_lo_conserva(admin, hacer_tarea):
    c, _ = admin
    t = hacer_tarea("UAF")
    otro = valor("estado", "Otro")
    c.post(f"/admin/catalogos/{otro.id}/estado", data={"activo": "0"})
    assert not db.session.get(Catalogo, otro.id).activo
    assert ">Otro<" not in c.get("/tareas/nueva").get_data(as_text=True)
    # una tarea que ya lo tiene lo sigue mostrando al editarla
    t.estado_id = otro.id
    db.session.commit()
    assert ">Otro<" in c.get(f"/tareas/{t.id}/editar").get_data(as_text=True)


def test_eliminar_solo_si_no_se_usa(admin, hacer_tarea):
    c, _ = admin
    hacer_tarea("UAF")  # usa «Pendiente» y «Solicitud al MRE»
    pendiente, otro = valor("estado", "Pendiente"), valor("estado", "Otro")
    c.post(f"/admin/catalogos/{pendiente.id}/eliminar")
    assert db.session.get(Catalogo, pendiente.id) is not None
    c.post(f"/admin/catalogos/{otro.id}/eliminar")
    assert db.session.get(Catalogo, otro.id) is None


def test_mover_cambia_el_orden(admin):
    c, _ = admin
    antes = [x.valor for x in srv.valores("prioridad")]
    assert antes == ["Alta", "Media", "Baja"]
    c.post(f"/admin/catalogos/{valor('prioridad', 'Baja').id}/mover", data={"direccion": "subir"})
    assert [x.valor for x in srv.valores("prioridad")] == ["Alta", "Baja", "Media"]
    c.post(f"/admin/catalogos/{valor('prioridad', 'Alta').id}/mover", data={"direccion": "subir"})  # ya es el primero
    assert [x.valor for x in srv.valores("prioridad")] == ["Alta", "Baja", "Media"]
    # se audita el movimiento real; el que no cambia nada no deja registro
    assert Auditoria.query.filter_by(accion="mover_catalogo").count() == 1


@pytest.mark.parametrize("rol,sigla", [("supervisor", None), ("unidad", "UAF"), ("invitado", None)])
def test_solo_admin(como, rol, sigla):
    c, _ = como(rol, sigla)
    otro = valor("estado", "Otro")
    assert c.get("/admin/catalogos").status_code == 403
    assert c.post("/admin/catalogos/estado/agregar", data={"valor": "X"}).status_code == 403
    assert c.post(f"/admin/catalogos/{otro.id}/eliminar").status_code == 403
    assert db.session.get(Catalogo, otro.id) is not None
