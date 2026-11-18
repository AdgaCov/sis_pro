from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.utils.fechas import ahora_utc
from tests.conftest import CLAVE, ingresar


def test_login_correcto(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    r = ingresar(client, u)
    assert r.status_code == 302 and r.headers["Location"] == "/"
    assert client.get("/").status_code == 200


def test_login_no_distingue_mayusculas(client, hacer_usuario):
    hacer_usuario("unidad", "UAF", nombre="jperez")
    assert ingresar(client, "JPerez").status_code == 302
    assert client.get("/").status_code == 200


def test_login_incorrecto(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    r = ingresar(client, u, "malaClave1")
    assert r.status_code == 200
    assert "Usuario o contraseña incorrectos." in r.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_usuario_inexistente_mismo_mensaje(client):
    r = ingresar(client, "noexiste", "Clave1234")
    assert "Usuario o contraseña incorrectos." in r.get_data(as_text=True)


def test_usuario_inactivo_no_entra(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    u.activo = False
    db.session.commit()
    assert ingresar(client, u).status_code == 200
    assert client.get("/").status_code == 302


def test_bloqueo_tras_5_intentos(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    for _ in range(5):
        ingresar(client, u, "malaClave1")
    db.session.refresh(u)
    assert u.esta_bloqueado
    r = ingresar(client, u)  # clave correcta, pero bloqueado
    assert "bloqueado temporalmente" in r.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_bloqueo_expira(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    u.bloqueado_hasta = ahora_utc() - timedelta(minutes=1)
    db.session.commit()
    assert ingresar(client, u).status_code == 302
    assert client.get("/").status_code == 200


def test_4_intentos_y_acierto_reinicia_contador(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    for _ in range(4):
        ingresar(client, u, "malaClave1")
    ingresar(client, u)
    db.session.refresh(u)
    assert u.intentos_fallidos == 0 and not u.esta_bloqueado


# ------------------------------------------------------------------ clave temporal
def test_clave_temporal_obliga_a_cambiarla(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF", debe_cambiar=True)
    r = ingresar(client, u)
    assert r.headers["Location"] == "/cambiar-clave"
    for ruta in ["/", "/admin/usuarios"]:
        r = client.get(ruta)
        assert r.status_code == 302 and r.headers["Location"] == "/cambiar-clave"
    r = client.post("/cambiar-clave", data={"actual": CLAVE, "nueva": "Nueva2025x", "confirmar": "Nueva2025x"})
    assert r.status_code == 302
    db.session.refresh(u)
    assert not u.debe_cambiar_clave
    assert client.get("/").status_code == 200  # la sesión actual sigue válida


@pytest.mark.parametrize("nueva", ["corta1", "sololetras", "12345678", CLAVE])
def test_clave_nueva_invalida(client, hacer_usuario, nueva):
    u = hacer_usuario("unidad", "UAF", debe_cambiar=True)
    ingresar(client, u)
    r = client.post("/cambiar-clave", data={"actual": CLAVE, "nueva": nueva, "confirmar": nueva})
    assert r.status_code == 200
    db.session.refresh(u)
    assert u.debe_cambiar_clave


def test_clave_actual_incorrecta(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    ingresar(client, u)
    r = client.post("/cambiar-clave", data={"actual": "otra1234", "nueva": "Nueva2025x", "confirmar": "Nueva2025x"})
    assert "La contraseña actual no es correcta." in r.get_data(as_text=True)


# ------------------------------------------------------------------ sesión
def test_logout_solo_por_post(como):
    c, _ = como("unidad", "UAF")
    assert c.get("/logout").status_code == 405
    assert c.post("/logout").status_code == 302
    assert c.get("/").status_code == 302


def test_sesion_caduca_a_las_8_horas(como):
    c, _ = como("unidad", "UAF")
    with c.session_transaction() as s:
        s["ingreso_ts"] -= 8 * 3600 + 1
    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_restablecer_clave_cierra_sesiones(como):
    admin_c, _ = como("admin")
    otro_c, otro = como("unidad", "UAF")
    assert otro_c.get("/").status_code == 200
    r = admin_c.post(f"/admin/usuarios/{otro.id}/restablecer")
    assert r.status_code == 200
    r = otro_c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_desactivar_cierra_sesiones(como):
    admin_c, _ = como("admin")
    otro_c, otro = como("supervisor")
    admin_c.post(f"/admin/usuarios/{otro.id}/estado", data={"activo": "0"})
    assert otro_c.get("/").status_code == 302


def test_cambiar_rol_cierra_sesiones(como):
    admin_c, _ = como("admin")
    otro_c, otro = como("supervisor")
    admin_c.post(f"/admin/usuarios/{otro.id}/editar",
                 data={"nombre_completo": "X", "rol": "invitado", "unidad_id": "0"})
    assert otro_c.get("/").status_code == 302


def test_redireccion_next_externa_ignorada(client, hacer_usuario):
    u = hacer_usuario("unidad", "UAF")
    r = client.post("/login?next=//malicioso.com", data={"nombre_usuario": u.nombre_usuario, "clave": CLAVE})
    assert r.headers["Location"] == "/"


def test_csrf_obligatorio():
    app = create_app("pruebas")
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        db.create_all()
        try:
            r = app.test_client().post("/login", data={"nombre_usuario": "x", "clave": "y"})
            assert r.status_code == 400
        finally:
            db.drop_all()
