from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.usuarios import AccionForm
from app.models import Catalogo
from app.models.catalogo import TIPOS_CATALOGO
from app.models.usuario import ROL_ADMIN
from app.services import ErrorNegocio
from app.services import catalogos as srv
from app.utils.decoradores import rol_requerido

bp = Blueprint("admin_catalogos", __name__, url_prefix="/admin/catalogos")
ORDEN_TIPOS = ("estado", "tipo", "instancia", "prioridad", "area")


@bp.before_request
@rol_requerido(ROL_ADMIN)
def _solo_admin():
    return None


def _valor_o_404(catalogo_id: int) -> Catalogo:
    c = db.session.get(Catalogo, catalogo_id)
    if c is None:
        abort(404)
    return c


def _ejecutar(accion, tipo: str, exito: str | None = None):
    """Valida CSRF, ejecuta la acción del servicio y vuelve a la pestaña del catálogo."""
    if not AccionForm().validate_on_submit():
        abort(400)
    try:
        accion()
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    else:
        if exito:
            flash(exito, "success")
    return redirect(url_for(".lista", tipo=tipo))


@bp.route("")
def lista():
    tipo = request.args.get("tipo", ORDEN_TIPOS[0])
    if tipo not in TIPOS_CATALOGO:
        abort(404)
    return render_template("admin/catalogos/lista.html", tipo=tipo, tipos=ORDEN_TIPOS, nombres=srv.NOMBRES_TIPO,
                           valores=srv.valores(tipo), usos=srv.usos(tipo), accion=AccionForm())


@bp.route("/<tipo>/agregar", methods=["POST"])
def agregar(tipo: str):
    if tipo not in TIPOS_CATALOGO:
        abort(404)
    valor = request.form.get("valor", "")
    return _ejecutar(lambda: srv.agregar(current_user, tipo, valor), tipo, f"«{valor.strip()}» agregado.")


@bp.route("/<int:catalogo_id>/renombrar", methods=["POST"])
def renombrar(catalogo_id: int):
    c = _valor_o_404(catalogo_id)
    return _ejecutar(lambda: srv.renombrar(current_user, c, request.form.get("valor", "")), c.tipo, "Valor actualizado.")


@bp.route("/<int:catalogo_id>/estado", methods=["POST"])
def estado(catalogo_id: int):
    c = _valor_o_404(catalogo_id)
    activo = request.form.get("activo") == "1"
    return _ejecutar(lambda: srv.cambiar_estado(current_user, c, activo), c.tipo,
                     f"«{c.valor}» {'activado' if activo else 'desactivado'}.")


@bp.route("/<int:catalogo_id>/mover", methods=["POST"])
def mover(catalogo_id: int):
    c = _valor_o_404(catalogo_id)
    direccion = 1 if request.form.get("direccion") == "bajar" else -1
    return _ejecutar(lambda: srv.mover(current_user, c, direccion), c.tipo)


@bp.route("/<int:catalogo_id>/eliminar", methods=["POST"])
def eliminar(catalogo_id: int):
    c = _valor_o_404(catalogo_id)
    valor = c.valor
    return _ejecutar(lambda: srv.eliminar(current_user, c), c.tipo, f"«{valor}» eliminado.")
