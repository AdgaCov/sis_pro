from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.tareas import AdjuntoForm, FiltroTareasForm, TareaForm
from app.forms.usuarios import AccionForm
from app.models import Tarea
from app.models.catalogo import ESTADO_CONCLUIDO
from app.models.usuario import ROL_ADMIN
from app.services import ErrorNegocio, permisos
from app.services import archivos as srv_archivos
from app.services import alertas
from app.services import plantillas as srv_plantillas
from app.services import responsables as srv_resp
from app.services import resumen
from app.services import tareas as srv
from app.utils.decoradores import rol_requerido, solo_lectura
from app.utils.paginacion import Pagina

bp = Blueprint("tareas", __name__, url_prefix="/tareas")


@bp.before_request
def _vista_permitida():
    if current_user.is_authenticated and not permisos.puede_ver_vista(current_user, "tareas"):
        abort(403)


def _tarea_visible(tarea_id: int) -> Tarea:
    tarea = db.session.get(Tarea, tarea_id)
    # 404 también cuando no la puede ver: no revela que existe
    if tarea is None or not permisos.puede_ver_tarea(current_user, tarea):
        abort(404)
    return tarea


def _tarea_editable(tarea_id: int) -> Tarea:
    tarea = _tarea_visible(tarea_id)
    if not permisos.puede_editar_tarea(current_user, tarea):
        abort(403)
    return tarea


def _preparar_form(form: TareaForm, tarea: Tarea | None) -> None:
    unidad_id = tarea.unidad_id if tarea else current_user.unidad_id
    form.cargar_opciones(
        unidades=permisos.unidades_visibles(current_user),
        catalogos=srv.catalogos_para_formulario(tarea),
        cargos=srv_resp.cargos_asignables(current_user, unidad_id, tarea.responsable_id if tarea else None),
        tareas_habilitables=srv.tareas_habilitables(current_user, tarea, unidad_id),
        ve_todo=current_user.ve_todo,
    )


# ------------------------------------------------------------------ listado
def formulario_filtros() -> FiltroTareasForm:
    """Filtros por GET, con las opciones que el usuario puede ver. Lo usan también las vistas del tablero."""
    filtro = FiltroTareasForm(request.args)
    filtro.cargar_opciones(
        unidades=permisos.unidades_visibles(current_user),
        catalogos=srv.catalogos_para_formulario(),
        cargos=srv_resp.cargos_asignables(current_user, current_user.unidad_id) if not current_user.es_invitado else [],
        ve_todo=current_user.ve_todo or current_user.es_invitado,
    )
    return filtro


def texto_filtros(filtro) -> str:
    """Descripción legible de los filtros aplicados."""
    partes = []
    for nombre in ("unidad_id", "tipo_id", "estado_id", "prioridad_id", "instancia_id", "area_id",
                   "responsable_id", "alerta"):
        campo = filtro[nombre]
        if campo.data:
            etiqueta = next((l for v, l in campo.choices if v == campo.data), campo.data)
            partes.append(f"{campo.label.text}: {etiqueta}")
    if (filtro.texto.data or "").strip():
        partes.append(f"Búsqueda: «{filtro.texto.data.strip()}»")
    partes.append("incluye concluidas" if filtro.ver_concluidas.data else "solo abiertas")
    return " · ".join(partes)


@bp.route("")
def lista():
    filtro = formulario_filtros()
    infos = resumen.filtrar(resumen.cargar(current_user), filtro.data)
    pagina = Pagina(infos, request.args.get("pagina", 1, type=int), current_app.config["TAREAS_POR_PAGINA"])
    puede_crear = current_user.ve_todo or (current_user.es_unidad and current_user.unidad_id)
    return render_template("tareas/lista.html", pagina=pagina, filtro=filtro, puede_crear=puede_crear,
                           plantilla_listado=srv_plantillas.vigente_para("listado"),
                           ficha=srv_plantillas.vigente_para("tarea"))


# ------------------------------------------------------------------ alta / edición
@bp.route("/nueva", methods=["GET", "POST"])
@solo_lectura
def nueva():
    if not (current_user.ve_todo or (current_user.es_unidad and current_user.unidad_id)):
        abort(403)
    form = TareaForm()
    _preparar_form(form, None)
    if request.method == "GET":
        pendiente = srv.estado_por_nombre("Pendiente")
        form.estado_id.data = pendiente.id if pendiente else None
        form.unidad_id.data = current_user.unidad_id
    if form.validate_on_submit():
        try:
            tarea = srv.guardar_tarea(current_user, form.datos())
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            flash(f"Tarea {tarea.codigo} creada.", "success")
            return redirect(url_for(".detalle", tarea_id=tarea.id))
    return render_template("tareas/form.html", form=form, tarea=None)


@bp.route("/<int:tarea_id>/editar", methods=["GET", "POST"])
@solo_lectura
def editar(tarea_id: int):
    tarea = _tarea_editable(tarea_id)
    form = TareaForm(obj=tarea)
    _preparar_form(form, tarea)
    if form.validate_on_submit():
        codigo = tarea.codigo
        try:
            srv.guardar_tarea(current_user, form.datos(), tarea)
        except ErrorNegocio as e:
            db.session.rollback()
            flash(str(e), "danger")
        else:
            if tarea.codigo != codigo:
                flash(f"Tarea reasignada: {codigo} ahora es {tarea.codigo}.", "success")
            else:
                flash(f"Tarea {tarea.codigo} guardada.", "success")
            return redirect(url_for(".detalle", tarea_id=tarea.id))
    return render_template("tareas/form.html", form=form, tarea=tarea)


# ------------------------------------------------------------------ detalle
@bp.route("/<int:tarea_id>")
def detalle(tarea_id: int):
    tarea = _tarea_visible(tarea_id)
    habilitada_por = permisos.consulta_tareas(current_user).filter(Tarea.habilita_a_id == tarea.id).all()
    abiertas = [h.codigo for h in habilitada_por if h.estado.valor != ESTADO_CONCLUIDO]
    return render_template(
        "tareas/detalle.html", tarea=tarea, habilitada_por=habilitada_por, info=alertas.info(tarea, bloqueada_por=abiertas),
        puede_editar=permisos.puede_editar_tarea(current_user, tarea),
        ve_adjuntos=permisos.puede_ver_adjuntos(current_user, tarea),
        accion=AccionForm(), form_adjunto=AdjuntoForm(), ficha=srv_plantillas.vigente_para("tarea"),
        ve_habilita=tarea.habilita_a is not None and permisos.puede_ver_tarea(current_user, tarea.habilita_a),
    )


@bp.route("/<int:tarea_id>/eliminar", methods=["POST"])
@solo_lectura
def eliminar(tarea_id: int):
    tarea = _tarea_editable(tarea_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    codigo = tarea.codigo
    try:
        srv.eliminar_tarea(current_user, tarea)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
        return redirect(url_for(".detalle", tarea_id=tarea_id))
    flash(f"Tarea {codigo} eliminada. Queda una copia en la papelera.", "success")
    return redirect(url_for(".lista"))


@bp.route("/<int:tarea_id>/subtareas/<int:subtarea_id>", methods=["POST"])
@solo_lectura
def marcar_subtarea(tarea_id: int, subtarea_id: int):
    tarea = _tarea_editable(tarea_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    try:
        srv.marcar_subtarea(current_user, tarea, subtarea_id, request.form.get("hecho") == "1")
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for(".detalle", tarea_id=tarea_id) + "#subtareas")


# ------------------------------------------------------------------ adjuntos
@bp.route("/<int:tarea_id>/adjuntos", methods=["POST"])
@solo_lectura
def subir_adjunto(tarea_id: int):
    tarea = _tarea_editable(tarea_id)
    form = AdjuntoForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        adj = srv_archivos.guardar_adjunto(current_user, tarea, form.archivo.data)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    else:
        flash(f"Archivo «{adj.nombre_original}» adjuntado.", "success")
    return redirect(url_for(".detalle", tarea_id=tarea_id) + "#adjuntos")


@bp.route("/<int:tarea_id>/adjuntos/<int:adjunto_id>")
def descargar_adjunto(tarea_id: int, adjunto_id: int):
    tarea = _tarea_visible(tarea_id)
    if not permisos.puede_ver_adjuntos(current_user, tarea):
        abort(403)
    adjunto = srv.adjunto_de(tarea, adjunto_id)
    if adjunto is None:
        abort(404)
    try:
        ruta = srv_archivos.ruta_absoluta(adjunto)
    except ErrorNegocio:
        abort(404)
    if not ruta.is_file():
        abort(404)
    return send_file(ruta, as_attachment=True, download_name=adjunto.nombre_original,
                     mimetype=adjunto.tipo_mime or "application/octet-stream")


@bp.route("/<int:tarea_id>/adjuntos/<int:adjunto_id>/quitar", methods=["POST"])
@solo_lectura
def quitar_adjunto(tarea_id: int, adjunto_id: int):
    tarea = _tarea_editable(tarea_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    adjunto = srv.adjunto_de(tarea, adjunto_id)
    if adjunto is None:
        abort(404)
    nombre = adjunto.nombre_original
    try:
        srv_archivos.quitar_adjunto(current_user, tarea, adjunto)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
    else:
        flash(f"Archivo «{nombre}» quitado.", "success")
    return redirect(url_for(".detalle", tarea_id=tarea_id) + "#adjuntos")


# ------------------------------------------------------------------ papelera
@bp.route("/papelera")
@rol_requerido(ROL_ADMIN)
def papelera():
    return render_template("tareas/papelera.html", registros=srv.papelera())
