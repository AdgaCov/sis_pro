"""Control de acceso. Todo se valida en el servidor."""
import time
from functools import wraps

from flask import abort, current_app, flash, redirect, request, session, url_for
from flask_login import current_user, logout_user

from app.extensions import login_manager

METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}

# Accesibles sin sesión
ENDPOINTS_PUBLICOS = {"auth.login", "static"}
# Accesibles mientras el usuario debe cambiar su clave temporal
ENDPOINTS_CLAVE_TEMPORAL = {"auth.cambiar_clave", "auth.logout", "static"}
# Únicas escrituras permitidas a un invitado
ESCRITURAS_INVITADO = {"auth.logout", "auth.cambiar_clave"}


def rol_requerido(*roles):
    """Exige sesión y uno de los roles indicados; si no, 403."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.rol not in roles:
                abort(403)
            return vista(*args, **kwargs)

        return envoltura

    return decorador


def solo_lectura(vista):
    """Rechaza con 403 cualquier escritura de un invitado en esta vista."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        if (
            current_user.is_authenticated
            and current_user.es_invitado
            and request.method not in METODOS_LECTURA
            and request.endpoint not in ESCRITURAS_INVITADO
        ):
            abort(403)
        return vista(*args, **kwargs)

    return envoltura


def guardas_globales():
    """before_request de la aplicación: sesión obligatoria, caducidad, invitado y clave temporal."""
    endpoint = request.endpoint
    if endpoint is None:
        return None  # 404 lo resuelve Flask

    if not current_user.is_authenticated:
        if endpoint in ENDPOINTS_PUBLICOS:
            return None
        return login_manager.unauthorized()

    # Caducidad absoluta de la sesión (no se renueva con la actividad)
    inicio = session.get("ingreso_ts")
    if not inicio or time.time() - inicio > current_app.config["HORAS_SESION"] * 3600:
        logout_user()
        session.clear()
        flash("Su sesión expiró. Ingrese nuevamente.", "warning")
        return redirect(url_for("auth.login"))

    # Invitado: nunca escribe (aplica a todas las rutas, aunque falte el decorador)
    if current_user.es_invitado and request.method not in METODOS_LECTURA and endpoint not in ESCRITURAS_INVITADO:
        abort(403)

    # Clave temporal: solo puede cambiarla o salir
    if current_user.debe_cambiar_clave and endpoint not in ENDPOINTS_CLAVE_TEMPORAL:
        flash("Debe cambiar su contraseña temporal antes de continuar.", "warning")
        return redirect(url_for("auth.cambiar_clave"))
    return None
