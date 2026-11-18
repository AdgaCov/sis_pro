from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.invitados import PermisoInvitadoForm
from app.models import Unidad, Usuario
from app.models.usuario import ROL_ADMIN, ROL_INVITADO
from app.services import ErrorNegocio
from app.services import invitados as srv
from app.utils.decoradores import rol_requerido

bp = Blueprint("admin_invitados", __name__, url_prefix="/admin/invitados")


@bp.before_request
@rol_requerido(ROL_ADMIN)
def _solo_admin():
    return None


@bp.route("")
def lista():
    invitados = Usuario.query.filter_by(rol=ROL_INVITADO).order_by(Usuario.nombre_usuario).all()
    return render_template("admin/invitados/lista.html", invitados=invitados)


@bp.route("/<int:usuario_id>", methods=["GET", "POST"])
def editar(usuario_id: int):
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None or not usuario.es_invitado:
        abort(404)
    form = PermisoInvitadoForm()
    form.unidades.choices = [(u.id, f"{u.sigla} · {u.nombre}")
                             for u in Unidad.query.order_by(Unidad.orden, Unidad.sigla)]
    if request.method == "GET" and usuario.permiso_invitado:
        form.todas_unidades.data = usuario.permiso_invitado.todas_unidades
        form.unidades.data = [u.id for u in usuario.permiso_invitado.unidades]
    if form.validate_on_submit():
        try:
            srv.configurar(usuario, form.todas_unidades.data, form.unidades.data or [], current_user)
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash(f"Acceso de «{usuario.nombre_usuario}» actualizado.", "success")
            return redirect(url_for(".lista"))
    return render_template("admin/invitados/form.html", form=form, usuario=usuario)
