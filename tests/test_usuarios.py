import pytest

from app.extensions import db
from app.models import Usuario
from app.services import ErrorNegocio
from app.services import usuarios as srv
from tests.conftest import ingresar, unidad


def test_admin_crea_usuario_con_su_clave(como):
    c, _ = como("admin")
    r = c.post("/admin/usuarios/nuevo", data={
        "nombre_usuario": "MLopez", "nombre_completo": "María López", "rol": "unidad",
        "unidad_id": str(unidad("UAF").id), "clave": "Mlopez2026", "confirmar": "Mlopez2026",
    })
    assert r.status_code == 302
    u = Usuario.query.filter_by(nombre_usuario="mlopez").one()
    assert u.verificar_clave("Mlopez2026") and not u.debe_cambiar_clave
    assert u.unidad.sigla == "UAF"
    # puede entrar directo con esa clave
    c2 = c.application.test_client()
    assert ingresar(c2, "mlopez", "Mlopez2026").headers["Location"].endswith("/")


def test_admin_crea_usuario_y_pide_cambio(como):
    c, _ = como("admin")
    c.post("/admin/usuarios/nuevo", data={
        "nombre_usuario": "jruiz", "nombre_completo": "Juan Ruiz", "rol": "supervisor", "unidad_id": "0",
        "clave": "Jruiz2026x", "confirmar": "Jruiz2026x", "debe_cambiar": "y",
    })
    assert Usuario.query.filter_by(nombre_usuario="jruiz").one().debe_cambiar_clave


@pytest.mark.parametrize("clave,confirmar", [("Corta1", "Corta1"), ("SoloLetras", "SoloLetras"),
                                             ("Clave1234", "Clave9999"), ("", "")])
def test_crear_usuario_rechaza_clave_invalida(como, clave, confirmar):
    c, _ = como("admin")
    r = c.post("/admin/usuarios/nuevo", data={
        "nombre_usuario": "malo", "nombre_completo": "Malo", "rol": "supervisor", "unidad_id": "0",
        "clave": clave, "confirmar": confirmar,
    })
    assert r.status_code == 200
    assert Usuario.query.filter_by(nombre_usuario="malo").first() is None


def test_unidad_obligatoria_para_rol_unidad(app):
    with pytest.raises(ErrorNegocio, match="unidad asignada"):
        srv.crear_usuario("abc", "Abc", "unidad", None, None)


def test_usuario_duplicado_sin_importar_mayusculas(app):
    srv.crear_usuario("jperez", "Juan", "supervisor", None, None)
    with pytest.raises(ErrorNegocio, match="Ya existe"):
        srv.crear_usuario("JPEREZ", "Juan 2", "supervisor", None, None)


@pytest.mark.parametrize("nombre", ["ab", "con espacio", "ñandú", "a" * 51])
def test_nombre_usuario_invalido(app, nombre):
    with pytest.raises(ErrorNegocio):
        srv.crear_usuario(nombre, "X", "supervisor", None, None)


@pytest.mark.parametrize("clave,valida", [
    ("abc12345", True), ("Clave1234", True), ("abcdefgh", False), ("12345678", False), ("ab1", False), ("", False),
])
def test_validar_clave(clave, valida):
    if valida:
        srv.validar_clave(clave)
    else:
        with pytest.raises(ErrorNegocio):
            srv.validar_clave(clave)


def test_clave_temporal_generada_es_valida():
    for _ in range(50):
        srv.validar_clave(srv.generar_clave_temporal())


def test_invitado_recibe_permisos_vacios_y_se_quitan_al_cambiar_rol(app, hacer_usuario):
    admin = hacer_usuario("admin")
    inv, _ = srv.crear_usuario("visita", "Visita", "invitado", None, admin)
    p = inv.permiso_invitado
    assert p is not None and not any([p.ver_resumen, p.ver_tareas, p.todas_unidades, p.ver_adjuntos])
    srv.actualizar_usuario(inv, "Visita", "supervisor", None, admin)
    assert inv.permiso_invitado is None


def test_restablecer_clave(app, hacer_usuario):
    admin = hacer_usuario("admin")
    u = hacer_usuario("unidad", "UPT")
    u.intentos_fallidos = 3
    version = u.version_sesion
    clave = srv.restablecer_clave(u, admin)
    assert u.verificar_clave(clave) and u.debe_cambiar_clave
    assert u.version_sesion == version + 1 and u.intentos_fallidos == 0


def test_admin_no_restablece_su_propia_clave(app, hacer_usuario):
    admin = hacer_usuario("admin")
    with pytest.raises(ErrorNegocio):
        srv.restablecer_clave(admin, admin)


# ------------------------------------------------------------------ siempre un admin activo
def test_no_se_desactiva_el_ultimo_admin(app, hacer_usuario):
    admin = hacer_usuario("admin")
    otro_admin_inactivo = hacer_usuario("admin")
    otro_admin_inactivo.activo = False
    db.session.commit()
    supervisor = hacer_usuario("supervisor")
    # el supervisor no puede llegar aquí por la web; se prueba la regla del servicio
    with pytest.raises(ErrorNegocio, match="al menos un administrador"):
        srv.cambiar_estado(admin, False, supervisor)


def test_admin_no_se_desactiva_a_si_mismo(app, hacer_usuario):
    admin = hacer_usuario("admin")
    hacer_usuario("admin")
    with pytest.raises(ErrorNegocio, match="propio usuario"):
        srv.cambiar_estado(admin, False, admin)


def test_no_se_quita_el_rol_al_ultimo_admin(app, hacer_usuario):
    admin = hacer_usuario("admin")
    with pytest.raises(ErrorNegocio, match="al menos un administrador"):
        srv.actualizar_usuario(admin, "Yo", "supervisor", None, admin)
    db.session.rollback()
    assert db.session.get(Usuario, admin.id).rol == "admin"


def test_con_dos_admins_se_puede_desactivar_uno(app, hacer_usuario):
    a1 = hacer_usuario("admin")
    a2 = hacer_usuario("admin")
    srv.cambiar_estado(a2, False, a1)
    assert not a2.activo


def test_pantalla_desactivar_ultimo_admin_muestra_error(como, hacer_usuario):
    c, admin = como("admin")
    r = c.post(f"/admin/usuarios/{admin.id}/estado", data={"activo": "0"}, follow_redirects=True)
    assert "No puede desactivar su propio usuario." in r.get_data(as_text=True)
    db.session.refresh(admin)
    assert admin.activo
