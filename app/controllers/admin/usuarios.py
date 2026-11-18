from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.usuarios import AccionForm, EditarUsuarioForm, NuevoUsuarioForm
from app.models import Unidad, Usuario
from app.models.usuario import ROL_ADMIN
from app.services import ErrorNegocio
from app.services import usuarios as srv
from app.utils.decoradores import rol_requerido

bp = Blueprint("admin_usuarios", __name__, url_prefix="/admin/usuarios")


@bp.before_request
@rol_requerido(ROL_ADMIN)
def _solo_admin():
    return None


def _unidades():
    return Unidad.query.order_by(Unidad.orden, Unidad.sigla).all()


def _usuario_o_404(usuario_id: int) -> Usuario:
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        abort(404)
    return usuario


@bp.route("")
def lista():
    usuarios = Usuario.query.order_by(Usuario.rol, Usuario.nombre_usuario).all()
    return render_template("admin/usuarios/lista.html", usuarios=usuarios, accion=AccionForm())


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    form = NuevoUsuarioForm()
    form.cargar_unidades(_unidades())
    if form.validate_on_submit():
        try:
            usuario, _ = srv.crear_usuario(
                form.nombre_usuario.data, form.nombre_completo.data, form.rol.data,
                form.unidad_id.data or None, current_user,
                clave=form.clave.data, debe_cambiar=form.debe_cambiar.data,
            )
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash(f"Usuario «{usuario.nombre_usuario}» creado con la contraseña indicada.", "success")
            if usuario.es_invitado:
                flash("Indique qué unidades verá este invitado en el resumen ejecutivo.", "info")
                return redirect(url_for("admin_invitados.editar", usuario_id=usuario.id))
            return redirect(url_for(".lista"))
    return render_template("admin/usuarios/form.html", form=form, usuario=None)


@bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
def editar(usuario_id: int):
    usuario = _usuario_o_404(usuario_id)
    form = EditarUsuarioForm(obj=usuario)
    form.cargar_unidades(_unidades())
    if request.method == "GET":
        form.unidad_id.data = usuario.unidad_id or 0
    if form.validate_on_submit():
        try:
            srv.actualizar_usuario(usuario, form.nombre_completo.data, form.rol.data,
                                   form.unidad_id.data or None, current_user)
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash(f"Usuario «{usuario.nombre_usuario}» actualizado.", "success")
            return redirect(url_for(".lista"))
    return render_template("admin/usuarios/form.html", form=form, usuario=usuario)


@bp.route("/<int:usuario_id>/restablecer", methods=["POST"])
def restablecer(usuario_id: int):
    usuario = _usuario_o_404(usuario_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    try:
        clave = srv.restablecer_clave(usuario, current_user)
    except ErrorNegocio as e:
        flash(str(e), "danger")
        return redirect(url_for(".lista"))
    return render_template("admin/usuarios/clave_temporal.html", usuario=usuario, clave=clave, nuevo=False)


@bp.route("/<int:usuario_id>/estado", methods=["POST"])
def estado(usuario_id: int):
    usuario = _usuario_o_404(usuario_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    activar = request.form.get("activo") == "1"
    try:
        srv.cambiar_estado(usuario, activar, current_user)
    except ErrorNegocio as e:
        flash(str(e), "danger")
    else:
        flash(f"Usuario «{usuario.nombre_usuario}» {'activado' if activar else 'desactivado'}.", "success")
    return redirect(url_for(".lista"))
