import io
import itertools

import docx

import pytest
from flask import g

from app import create_app
from app.cli import cargar_catalogos
from app.extensions import db
from app.models import Catalogo, PermisoInvitado, Plantilla, Tarea, Unidad, Usuario

CLAVE = "Clave1234"
_contador = itertools.count(1)


@pytest.fixture
def app(tmp_path):
    app = create_app("pruebas")
    app.config["STORAGE_DIR"] = tmp_path  # los adjuntos de prueba no tocan storage/

    # El contexto de la app queda abierto durante el test y las peticiones lo reutilizan;
    # Flask-Login guarda el usuario en `g`, así que se limpia en cada petición como en producción.
    @app.teardown_request
    def _limpiar_usuario(_exc):
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        cargar_catalogos()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def unidad(sigla: str) -> Unidad:
    return Unidad.query.filter_by(sigla=sigla).one()


@pytest.fixture
def hacer_usuario(app):
    """Crea un usuario con clave CLAVE. Para invitados acepta permisos: hacer_usuario('invitado', permisos={...})."""

    def _hacer(rol, sigla=None, nombre=None, debe_cambiar=False, permisos=None, unidades_invitado=()):
        n = next(_contador)
        u = Usuario(
            nombre_usuario=nombre or f"{rol}{n}",
            nombre_completo=f"Persona {n}",
            rol=rol,
            unidad_id=unidad(sigla).id if sigla else None,
            debe_cambiar_clave=debe_cambiar,
            activo=True,
            intentos_fallidos=0,
            version_sesion=1,
        )
        u.poner_clave(CLAVE)
        if rol == "invitado":
            u.permiso_invitado = PermisoInvitado(**(permisos or {}))
            u.permiso_invitado.unidades = [unidad(s) for s in unidades_invitado]
        db.session.add(u)
        db.session.commit()
        return u

    return _hacer


@pytest.fixture
def hacer_tarea(app):
    def _hacer(sigla: str) -> Tarea:
        un = unidad(sigla)
        un.ultimo_correlativo += 1
        t = Tarea(
            codigo=f"{un.sigla}-{un.ultimo_correlativo:03d}",
            unidad_id=un.id,
            tipo_id=Catalogo.query.filter_by(tipo="tipo", valor="Solicitud al MRE").one().id,
            estado_id=Catalogo.query.filter_by(tipo="estado", valor="Pendiente").one().id,
            asunto=f"Asunto de {un.sigla}",
        )
        db.session.add(t)
        db.session.commit()
        return t

    return _hacer


def ingresar(client, usuario, clave=CLAVE):
    nombre = usuario if isinstance(usuario, str) else usuario.nombre_usuario
    return client.post("/login", data={"nombre_usuario": nombre, "clave": clave})


@pytest.fixture
def como(app, hacer_usuario):
    """Devuelve un cliente con sesión iniciada para el rol pedido."""

    def _como(rol, sigla=None, **kw):
        c = app.test_client()
        u = hacer_usuario(rol, sigla, **kw)
        resp = ingresar(c, u)
        assert resp.status_code == 302
        return c, u

    return _como


@pytest.fixture
def poner_plantilla(como):
    """Sube como admin una plantilla Word con esos párrafos: poner_plantilla('resumen', '{{ unidad.nombre }}')."""
    admin, _ = como("admin")

    def _poner(alcance, *parrafos):
        d = docx.Document()
        for texto in parrafos:
            d.add_paragraph(texto)
        buf = io.BytesIO()
        d.save(buf)
        r = admin.post("/admin/plantillas/nueva", data={
            "nombre": f"Plantilla {alcance}", "alcance": alcance, "archivo": (io.BytesIO(buf.getvalue()), f"{alcance}.docx"),
        }, content_type="multipart/form-data")
        assert r.status_code == 302
        return Plantilla.query.filter_by(alcance=alcance).order_by(Plantilla.id.desc()).first()

    return _poner


@pytest.fixture
def pdf_como_texto(monkeypatch):
    """El «PDF» trae el texto del documento ya llenado, para buscar datos en la descarga
    (el PDF real guarda el texto con fuentes incrustadas y no se puede buscar en los bytes)."""
    from app.services import pdf

    def convertir(datos, extension):
        d = docx.Document(io.BytesIO(datos))
        texto = "\n".join([x.text for x in d.paragraphs] + [c.text for t in d.tables for f in t.rows for c in f.cells])
        return b"%PDF-texto\n" + texto.encode("utf-8")

    monkeypatch.setattr(pdf, "convertir_a_pdf", convertir)
