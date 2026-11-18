"""Etapa 2: cargos responsables."""
import pytest

from app.extensions import db
from app.models import Cargo
from tests.conftest import unidad


def cargo(sigla, nombre="Apoyo"):
    return Cargo.query.filter_by(unidad_id=unidad(sigla).id, nombre=nombre).one()


def test_unidad_ve_solo_sus_cargos(como):
    c, _ = como("unidad", "UAF")
    html = c.get("/responsables").get_data(as_text=True)
    assert "Jefe Administrativo Financiero" in html and "Técnico en Fotografía" not in html


def test_unidad_crea_cargo_solo_en_su_unidad(como):
    c, _ = como("unidad", "UAF")
    c.post("/responsables/nuevo", data={"unidad_id": unidad("UPT").id, "nombre": "Chofer", "persona": "Ana"})
    nuevo = Cargo.query.filter_by(nombre="Chofer").one()
    assert nuevo.unidad.sigla == "UAF" and nuevo.persona == "Ana"


def test_cargo_duplicado(como):
    c, _ = como("unidad", "UAF")
    c.post("/responsables/nuevo", data={"nombre": "mensajero"})
    assert Cargo.query.filter(Cargo.nombre.ilike("mensajero")).count() == 1


def test_unidad_no_toca_cargos_ajenos(como):
    ajeno = cargo("UPT", "Técnico en Fotografía")
    c, _ = como("unidad", "UAF")
    assert c.post(f"/responsables/{ajeno.id}/persona", data={"persona": "X"}).status_code == 404
    assert c.post(f"/responsables/{ajeno.id}/estado", data={"activo": "0"}).status_code == 404
    assert db.session.get(Cargo, ajeno.id).persona is None


def test_poner_persona_y_desactivar(como):
    c, _ = como("unidad", "UAF")
    m = cargo("UAF", "Mensajero")
    c.post(f"/responsables/{m.id}/persona", data={"persona": "Luis Pérez"})
    c.post(f"/responsables/{m.id}/estado", data={"activo": "0"})
    db.session.expire_all()
    m = db.session.get(Cargo, m.id)
    assert m.persona == "Luis Pérez" and not m.activo


def test_apoyo_no_se_desactiva_ni_se_mueve(como):
    c, _ = como("admin")
    apoyo = cargo("UAF")
    c.post(f"/responsables/{apoyo.id}/estado", data={"activo": "0"})
    c.post(f"/responsables/{apoyo.id}/mover", data={"unidad_id": unidad("UPT").id})
    db.session.expire_all()
    apoyo = db.session.get(Cargo, apoyo.id)
    assert apoyo.activo and apoyo.unidad.sigla == "UAF"


@pytest.mark.parametrize("rol,sigla", [("supervisor", None), ("unidad", "UAF")])
def test_solo_admin_mueve_cargos(como, rol, sigla):
    m = cargo("UAF", "Mensajero")
    c, _ = como(rol, sigla)
    assert c.post(f"/responsables/{m.id}/mover", data={"unidad_id": unidad("UPT").id}).status_code == 403


def test_admin_mueve_cargo(como):
    m = cargo("UAF", "Mensajero")
    c, _ = como("admin")
    c.post(f"/responsables/{m.id}/mover", data={"unidad_id": unidad("UPT").id})
    db.session.expire_all()
    assert db.session.get(Cargo, m.id).unidad.sigla == "UPT"


def test_invitado_no_entra_a_responsables(como):
    c, _ = como("invitado", permisos={"todas_unidades": True, "ver_tareas": True})
    assert c.get("/responsables").status_code == 403
    assert c.post("/responsables/nuevo", data={"nombre": "X"}).status_code == 403
