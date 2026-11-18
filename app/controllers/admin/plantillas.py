import io

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.plantillas import PlantillaForm
from app.forms.usuarios import AccionForm
from app.models import Plantilla
from app.models.usuario import ROL_ADMIN
from app.services import ErrorNegocio, pdf
from app.services import plantillas as srv
from app.utils.decoradores import rol_requerido

bp = Blueprint("admin_plantillas", __name__, url_prefix="/admin/plantillas")


@bp.before_request
@rol_requerido(ROL_ADMIN)
def _solo_admin():
    return None


def _plantilla_o_404(plantilla_id: int) -> Plantilla:
    p = db.session.get(Plantilla, plantilla_id)
    if p is None:
        abort(404)
    return p


def _avisar_desconocidos(p: Plantilla) -> None:
    if p.marcadores_desconocidos:
        flash("Marcadores desconocidos (quedarán vacíos): " + ", ".join(p.marcadores_desconocidos)
              + ". Revise la lista de marcadores disponibles.", "warning")


@bp.route("")
def lista():
    plantillas = Plantilla.query.order_by(Plantilla.alcance, Plantilla.nombre).all()
    return render_template("admin/plantillas/lista.html", plantillas=plantillas, accion=AccionForm(),
                           hay_libreoffice=pdf.libreoffice_disponible())


@bp.route("/marcadores")
def marcadores():
    return render_template("admin/plantillas/marcadores.html", marcadores=srv.MARCADORES)


@bp.route("/nueva", methods=["GET", "POST"])
def nueva():
    form = PlantillaForm()
    if form.validate_on_submit():
        try:
            p = srv.guardar(current_user, form.nombre.data, form.descripcion.data, form.alcance.data,
                            form.archivo.data)
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash(f"Plantilla «{p.nombre}» guardada.", "success")
            _avisar_desconocidos(p)
            return redirect(url_for(".lista"))
    return render_template("admin/plantillas/form.html", form=form, plantilla=None)


@bp.route("/<int:plantilla_id>/editar", methods=["GET", "POST"])
def editar(plantilla_id: int):
    p = _plantilla_o_404(plantilla_id)
    form = PlantillaForm(obj=p)
    if form.validate_on_submit():
        try:
            srv.guardar(current_user, form.nombre.data, form.descripcion.data, form.alcance.data,
                        form.archivo.data, p)
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash(f"Plantilla «{p.nombre}» guardada.", "success")
            _avisar_desconocidos(p)
            return redirect(url_for(".lista"))
    return render_template("admin/plantillas/form.html", form=form, plantilla=p)


@bp.route("/<int:plantilla_id>/estado", methods=["POST"])
def estado(plantilla_id: int):
    p = _plantilla_o_404(plantilla_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    activar = request.form.get("activa") == "1"
    srv.cambiar_estado(current_user, p, activar)
    flash(f"Plantilla «{p.nombre}» {'activada' if activar else 'desactivada'}.", "success")
    return redirect(url_for(".lista"))


@bp.route("/<int:plantilla_id>/eliminar", methods=["POST"])
def eliminar(plantilla_id: int):
    p = _plantilla_o_404(plantilla_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    nombre = p.nombre
    srv.eliminar(current_user, p)
    flash(f"Plantilla «{nombre}» eliminada.", "success")
    return redirect(url_for(".lista"))


@bp.route("/<int:plantilla_id>/archivo")
def archivo(plantilla_id: int):
    """Descarga el archivo original de la plantilla, para editarlo."""
    p = _plantilla_o_404(plantilla_id)
    ruta = srv.ruta_archivo(p)
    if not ruta.is_file():
        abort(404)
    return send_file(ruta, as_attachment=True, download_name=p.nombre_original, mimetype=srv.MIMES[p.formato])


@bp.route("/<int:plantilla_id>/probar")
def probar(plantilla_id: int):
    """Genera la plantilla con datos de ejemplo."""
    p = _plantilla_o_404(plantilla_id)
    try:
        datos, ext = srv.documento(p, srv.contexto_ejemplo(current_user), request.args.get("formato", "original"))
    except ErrorNegocio as e:
        flash(str(e), "danger")
        return redirect(url_for(".lista"))
    return send_file(io.BytesIO(datos), as_attachment=True, mimetype=srv.MIMES[ext],
                     download_name=srv.nombre_descarga(p, "prueba", ext))
