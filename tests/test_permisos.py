"""Permisos: una unidad no ve otra unidad, un invitado no puede escribir, solo el admin administra usuarios."""
import pytest
from flask_login import current_user

from app.extensions import db
from app.services import permisos
from app.utils.decoradores import solo_lectura

RUTAS_ADMIN_GET = ["/admin/usuarios", "/admin/usuarios/nuevo", "/admin/usuarios/1/editar"]
RUTAS_ADMIN_POST = ["/admin/usuarios/nuevo", "/admin/usuarios/1/restablecer", "/admin/usuarios/1/estado",
                    "/admin/usuarios/1/editar"]


# ------------------------------------------------------------------ admin de usuarios
@pytest.mark.parametrize("rol,sigla", [("supervisor", None), ("unidad", "UAF"), ("invitado", None)])
def test_admin_usuarios_prohibido_para_otros_roles(como, hacer_usuario, rol, sigla):
    hacer_usuario("admin")  # id 1 existe
    c, _ = como(rol, sigla)
    for ruta in RUTAS_ADMIN_GET:
        assert c.get(ruta).status_code == 403, ruta
    for ruta in RUTAS_ADMIN_POST:
        assert c.post(ruta, data={"activo": "0"}).status_code == 403, ruta


def test_admin_entra_a_usuarios(como):
    c, _ = como("admin")
    assert c.get("/admin/usuarios").status_code == 200
    assert c.get("/admin/usuarios/nuevo").status_code == 200


def test_sin_sesion_redirige_al_login(client):
    for ruta in ["/", "/admin/usuarios", "/cambiar-clave"]:
        r = client.get(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"], ruta


def test_supervisor_no_ve_enlace_usuarios(como):
    c, _ = como("supervisor")
    assert b"/admin/usuarios" not in c.get("/").data


# ------------------------------------------------------------------ invitado: solo lectura
@pytest.fixture
def rutas_escritura(app):
    """Rutas de prueba que aceptan POST: una sin decorador (guarda global) y otra con @solo_lectura."""

    def sin_decorador():
        return "ok"

    @solo_lectura
    def con_decorador():
        return "ok"

    app.add_url_rule("/_prueba/sin", "prueba_sin", sin_decorador, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    app.add_url_rule("/_prueba/con", "prueba_con", con_decorador, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])


@pytest.mark.parametrize("ruta", ["/_prueba/sin", "/_prueba/con"])
@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_invitado_no_puede_escribir(rutas_escritura, como, ruta, metodo):
    c, _ = como("invitado", permisos={"todas_unidades": True, "ver_tareas": True})
    assert getattr(c, metodo)(ruta).status_code == 403
    assert c.get(ruta).status_code == 200


@pytest.mark.parametrize("rol,sigla", [("admin", None), ("supervisor", None), ("unidad", "UAF")])
def test_otros_roles_si_pueden_escribir(rutas_escritura, como, rol, sigla):
    c, _ = como(rol, sigla)
    assert c.post("/_prueba/sin").status_code == 200
    assert c.post("/_prueba/con").status_code == 200


def test_solo_lectura_decorador_aislado(app, hacer_usuario):
    """El decorador rechaza aunque la guarda global no estuviera."""
    inv = hacer_usuario("invitado")

    @solo_lectura
    def vista():
        return "ok"

    from flask_login import login_user
    from werkzeug.exceptions import Forbidden

    with app.test_request_context("/x", method="POST"):
        login_user(inv)
        assert current_user.es_invitado
        with pytest.raises(Forbidden):
            vista()


def test_invitado_puede_cambiar_su_clave_y_salir(como):
    c, u = como("invitado")
    r = c.post("/cambiar-clave", data={"actual": "Clave1234", "nueva": "Otra5678x", "confirmar": "Otra5678x"})
    assert r.status_code == 302
    db.session.refresh(u)
    assert u.verificar_clave("Otra5678x")
    assert c.post("/logout").status_code == 302
    assert c.get("/").status_code == 302  # ya no tiene sesión


# ------------------------------------------------------------------ visibilidad de tareas por unidad
@pytest.fixture
def tareas(hacer_tarea):
    return {"UAF": hacer_tarea("UAF"), "UPT": hacer_tarea("UPT"), "UEP": hacer_tarea("UEP")}


def _codigos(usuario):
    return sorted(t.codigo for t in permisos.consulta_tareas(usuario).all())


def test_unidad_solo_ve_su_unidad(hacer_usuario, tareas):
    uaf = hacer_usuario("unidad", "UAF")
    upt = hacer_usuario("unidad", "UPT")
    assert _codigos(uaf) == ["UAF-001"]
    assert _codigos(upt) == ["UPT-001"]
    assert not permisos.puede_ver_tarea(uaf, tareas["UPT"])
    assert not permisos.puede_editar_tarea(uaf, tareas["UPT"])
    assert permisos.puede_editar_tarea(uaf, tareas["UAF"])
    assert [u.sigla for u in permisos.unidades_visibles(uaf)] == ["UAF"]


@pytest.mark.parametrize("rol", ["admin", "supervisor"])
def test_admin_y_supervisor_ven_y_editan_todo(hacer_usuario, tareas, rol):
    u = hacer_usuario(rol)
    assert _codigos(u) == ["UAF-001", "UEP-001", "UPT-001"]
    assert all(permisos.puede_editar_tarea(u, t) for t in tareas.values())
    assert permisos.puede_reasignar(u)


def test_unidad_no_puede_reasignar(hacer_usuario):
    assert not permisos.puede_reasignar(hacer_usuario("unidad", "UAF"))


def test_unidad_sin_unidad_no_ve_nada(hacer_usuario, tareas):
    u = hacer_usuario("unidad", "UAF")
    u.unidad_id = None
    assert _codigos(u) == []


def test_invitado_por_defecto_no_ve_nada(hacer_usuario, tareas):
    inv = hacer_usuario("invitado")
    assert _codigos(inv) == []
    assert not any(permisos.puede_ver_vista(inv, v) for v in ["resumen", "alertas", "informe", "cronograma", "tareas"])


def test_invitado_ve_solo_unidades_permitidas(hacer_usuario, tareas):
    inv = hacer_usuario("invitado", permisos={"ver_tareas": True}, unidades_invitado=["UPT", "UEP"])
    assert _codigos(inv) == ["UEP-001", "UPT-001"]
    assert permisos.puede_ver_vista(inv, "tareas")
    assert not permisos.puede_ver_vista(inv, "informe")


def test_invitado_todas_las_unidades_pero_nunca_edita(hacer_usuario, tareas):
    inv = hacer_usuario("invitado", permisos={"todas_unidades": True})
    assert _codigos(inv) == ["UAF-001", "UEP-001", "UPT-001"]
    assert not any(permisos.puede_editar_tarea(inv, t) for t in tareas.values())
    assert not permisos.puede_reasignar(inv)


def test_invitado_adjuntos_segun_permiso(hacer_usuario, tareas):
    sin = hacer_usuario("invitado", permisos={"todas_unidades": True})
    con = hacer_usuario("invitado", permisos={"todas_unidades": True, "ver_adjuntos": True})
    solo_upt = hacer_usuario("invitado", permisos={"ver_adjuntos": True}, unidades_invitado=["UPT"])
    assert not permisos.puede_ver_adjuntos(sin, tareas["UAF"])
    assert permisos.puede_ver_adjuntos(con, tareas["UAF"])
    assert not permisos.puede_ver_adjuntos(solo_upt, tareas["UAF"])  # no ve la unidad
    assert permisos.puede_ver_adjuntos(solo_upt, tareas["UPT"])


def test_usuario_inactivo_no_ve_nada(hacer_usuario, tareas):
    u = hacer_usuario("admin")
    u.activo = False
    assert _codigos(u) == []
    assert not permisos.puede_editar_tarea(u, tareas["UAF"])
