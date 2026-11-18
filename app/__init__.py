import os

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError

from app.extensions import csrf, db, login_manager, migrate
from config import CONFIGURACIONES


def create_app(nombre_config: str | None = None) -> Flask:
    app = Flask(__name__)
    nombre_config = nombre_config or os.getenv("APP_CONFIG", "desarrollo")
    app.config.from_object(CONFIGURACIONES[nombre_config])
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Falta SECRET_KEY en el archivo .env")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("Falta DATABASE_URL en el archivo .env")

    for sub in ("respaldos", "plantillas", "generados"):
        (app.config["STORAGE_DIR"] / sub).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    from app import models  # noqa: F401  (registra los modelos para Alembic)

    _registrar_sesion(app)
    _registrar_blueprints(app)
    _registrar_plantillas(app)
    _registrar_errores(app)

    from app.cli import registrar_comandos

    registrar_comandos(app)
    return app


def _registrar_sesion(app: Flask) -> None:
    from app.models import Usuario
    from app.utils.decoradores import guardas_globales

    @login_manager.user_loader
    def cargar_usuario(id_sesion: str):
        try:
            uid, version = (int(x) for x in id_sesion.split(":"))
        except (ValueError, AttributeError):
            return None
        usuario = db.session.get(Usuario, uid)
        if usuario is None or not usuario.activo or usuario.version_sesion != version:
            return None
        return usuario

    app.before_request(guardas_globales)

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp


def _registrar_blueprints(app: Flask) -> None:
    from app.controllers.admin.usuarios import bp as admin_usuarios_bp
    from app.controllers.auth import bp as auth_bp
    from app.controllers.inicio import bp as inicio_bp
    from app.controllers.responsables import bp as responsables_bp
    from app.controllers.tareas import bp as tareas_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(inicio_bp)
    app.register_blueprint(admin_usuarios_bp)
    app.register_blueprint(tareas_bp)
    app.register_blueprint(responsables_bp)


def _registrar_plantillas(app: Flask) -> None:
    from app.models.usuario import NOMBRES_ROL
    from app.services import permisos
    from app.utils.fechas import formato_fecha, formato_fecha_hora

    app.add_template_filter(formato_fecha, "fecha")
    app.add_template_filter(formato_fecha_hora, "fecha_hora")

    @app.context_processor
    def contexto():
        return {"NOMBRES_ROL": NOMBRES_ROL, "puede_ver_vista": permisos.puede_ver_vista}


def _registrar_errores(app: Flask) -> None:
    @app.errorhandler(403)
    def prohibido(_e):
        return render_template("errores/error.html", codigo=403,
                               mensaje="No tiene permiso para realizar esta acción."), 403

    @app.errorhandler(404)
    def no_encontrado(_e):
        return render_template("errores/error.html", codigo=404, mensaje="La página no existe."), 404

    @app.errorhandler(413)
    def muy_grande(_e):
        mb = app.config["MAX_MB_ADJUNTO"]
        return render_template("errores/error.html", codigo=413,
                               mensaje=f"El archivo supera {mb} MB."), 413

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_template("errores/error.html", codigo=400,
                               mensaje="El formulario expiró. Recargue la página e intente de nuevo."), 400
