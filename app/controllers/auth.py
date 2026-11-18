import time
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from app.forms.auth import CambiarClaveForm
from app.forms.auth import LoginForm
from app.services import ErrorNegocio
from app.services import usuarios as srv

bp = Blueprint("auth", __name__)


def _destino_seguro(url: str | None) -> str | None:
    if not url or "\\" in url:
        return None
    partes = urlsplit(url)
    if partes.scheme or partes.netloc or not url.startswith("/") or url.startswith("//"):
        return None
    return url


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("inicio.index"))
    form = LoginForm()
    if form.validate_on_submit():
        try:
            usuario = srv.autenticar(form.nombre_usuario.data, form.clave.data)
        except ErrorNegocio as e:
            flash(str(e), "danger")
        else:
            destino = _destino_seguro(request.args.get("next"))
            session.clear()  # evita fijación de sesión
            login_user(usuario)
            session.permanent = True
            session["ingreso_ts"] = time.time()
            if usuario.debe_cambiar_clave:
                return redirect(url_for("auth.cambiar_clave"))
            return redirect(destino or url_for("inicio.index"))
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/cambiar-clave", methods=["GET", "POST"])
def cambiar_clave():
    form = CambiarClaveForm()
    if form.validate_on_submit():
        usuario = current_user._get_current_object()
        try:
            srv.cambiar_clave_propia(usuario, form.actual.data, form.nueva.data)
        except ErrorNegocio as e:
            flash(str(e), "danger")
        else:
            login_user(usuario)  # renueva la sesión actual con la nueva versión
            flash("Contraseña actualizada.", "success")
            return redirect(url_for("inicio.index"))
    return render_template("auth/cambiar_clave.html", form=form, obligatorio=current_user.debe_cambiar_clave)
