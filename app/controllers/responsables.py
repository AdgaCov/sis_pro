from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.responsables import MoverCargoForm, NuevoCargoForm, PersonaForm
from app.forms.usuarios import AccionForm
from app.models import Cargo, Unidad
from app.services import ErrorNegocio, permisos
from app.services import responsables as srv
from app.utils.decoradores import solo_lectura

bp = Blueprint("responsables", __name__, url_prefix="/responsables")


@bp.before_request
def _sin_invitados():
    # Los invitados no ven la gestión de cargos
    if current_user.is_authenticated and current_user.es_invitado:
        abort(403)


def _cargo_editable(cargo_id: int) -> Cargo:
    cargo = db.session.get(Cargo, cargo_id)
    if cargo is None or not permisos.puede_ver_unidad(current_user, cargo.unidad_id):
        abort(404)
    if not permisos.puede_editar_unidad(current_user, cargo.unidad_id):
        abort(403)
    return cargo


def _volver(cargo: Cargo | None = None):
    destino = url_for(".lista")
    return redirect(destino + (f"#unidad-{cargo.unidad_id}" if cargo else ""))


@bp.route("")
def lista():
    unidades = permisos.unidades_visibles(current_user)
    ids = [c.id for u in unidades for c in u.cargos]
    form = NuevoCargoForm()
    form.unidad_id.choices = [(u.id, u.nombre) for u in unidades if permisos.puede_editar_unidad(current_user, u.id)]
    mover = MoverCargoForm()
    mover.unidad_id.choices = [(u.id, u.sigla) for u in Unidad.query.order_by(Unidad.orden, Unidad.sigla)]
    return render_template(
        "responsables/lista.html", unidades=unidades, abiertas=srv.tareas_abiertas_por_cargo(ids),
        form=form, mover=mover, accion=AccionForm(),
        puede_editar=lambda u: permisos.puede_editar_unidad(current_user, u.id),
    )


@bp.route("/nuevo", methods=["POST"])
@solo_lectura
def nuevo():
    form = NuevoCargoForm()
    form.unidad_id.choices = [(u.id, u.sigla) for u in Unidad.query.all()]
    if not current_user.ve_todo:
        form.unidad_id.data = current_user.unidad_id
    if not form.validate_on_submit():
        for errores in form.errors.values():
            flash(errores[0], "danger")
        return _volver()
    try:
        cargo = srv.crear_cargo(current_user, form.unidad_id.data, form.nombre.data, form.persona.data)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
        return _volver()
    flash(f"Cargo «{cargo.nombre}» agregado.", "success")
    return _volver(cargo)


@bp.route("/<int:cargo_id>/persona", methods=["POST"])
@solo_lectura
def persona(cargo_id: int):
    cargo = _cargo_editable(cargo_id)
    form = PersonaForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        srv.poner_persona(current_user, cargo, form.persona.data)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    else:
        flash(f"Persona designada en «{cargo.nombre}» actualizada.", "success")
    return _volver(cargo)


@bp.route("/<int:cargo_id>/estado", methods=["POST"])
@solo_lectura
def estado(cargo_id: int):
    cargo = _cargo_editable(cargo_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    activar = request.form.get("activo") == "1"
    try:
        srv.cambiar_estado(current_user, cargo, activar)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    else:
        flash(f"Cargo «{cargo.nombre}» {'activado' if activar else 'desactivado'}.", "success")
    return _volver(cargo)


@bp.route("/<int:cargo_id>/mover", methods=["POST"])
@solo_lectura
def mover(cargo_id: int):
    cargo = _cargo_editable(cargo_id)  # 404 si no lo ve: no revela cargos de otras unidades
    if not current_user.es_admin:
        abort(403)
    form = MoverCargoForm()
    form.unidad_id.choices = [(u.id, u.sigla) for u in Unidad.query.all()]
    if not form.validate_on_submit():
        abort(400)
    try:
        srv.mover_cargo(current_user, cargo, form.unidad_id.data)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    else:
        flash(f"Cargo «{cargo.nombre}» movido a {cargo.unidad.sigla}.", "success")
    return _volver(cargo)
