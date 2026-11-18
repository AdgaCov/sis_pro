from app.models import Cargo, Catalogo, Unidad, Usuario


def test_cargar_catalogos_es_idempotente(app):
    # conftest ya lo ejecutó una vez
    r = app.test_cli_runner().invoke(args=["cargar-catalogos"])
    assert r.exit_code == 0
    assert "Nuevos: 0 unidades, 0 cargos, 0 valores" in r.output
    assert Unidad.query.count() == 6
    for u in Unidad.query:
        assert Cargo.query.filter_by(unidad_id=u.id, nombre="Apoyo", es_apoyo=True).count() == 1


def test_catalogos_protegidos(app):
    protegidos = {(c.tipo, c.valor) for c in Catalogo.query.filter_by(protegido=True)}
    assert protegidos == {("tipo", "Tarea interna"), ("estado", "Concluido"), ("prioridad", "Alta")}
    assert Catalogo.query.filter_by(tipo="estado").count() == 12


def test_crear_admin(app):
    r = app.test_cli_runner().invoke(
        args=["crear-admin", "--usuario", "Plan", "--nombre", "Planificación", "--clave", "Inicio2025"]
    )
    assert r.exit_code == 0, r.output
    u = Usuario.query.filter_by(nombre_usuario="plan").one()
    assert u.es_admin and not u.debe_cambiar_clave and u.verificar_clave("Inicio2025")


def test_crear_admin_clave_debil(app):
    r = app.test_cli_runner().invoke(args=["crear-admin", "--usuario", "plan", "--nombre", "P", "--clave", "corta"])
    assert r.exit_code != 0
    assert "8 caracteres" in r.output
    assert Usuario.query.count() == 0
