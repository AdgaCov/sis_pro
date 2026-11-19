"""Generación de documentos desde plantillas. Los invitados no tienen acceso."""
import io

from flask import Blueprint, abort, flash, redirect, request, send_file, url_for
from flask_login import current_user

from app.controllers.tareas import formulario_filtros, texto_filtros
from app.extensions import db
from app.models import Plantilla, Tarea
from app.services import ErrorNegocio, agenda, alertas, auditoria, permisos, resumen
from app.services import plantillas as srv
from app.utils.fechas import a_local, ahora_utc, hoy_local

bp = Blueprint("documentos", __name__, url_prefix="/documentos")


@bp.before_request
def _sin_invitados():
    if current_user.is_authenticated and current_user.es_invitado:
        abort(403)


def _plantilla(plantilla_id: int, alcance: str) -> Plantilla:
    p = db.session.get(Plantilla, plantilla_id)
    if p is None or not p.activa or p.alcance != alcance:
        abort(404)
    return p


def _entregar(p: Plantilla, ctx: dict, sufijo: str, volver: str):
    formato = request.args.get("formato", "original")
    try:
        datos, ext = srv.documento(p, ctx, formato)
    except ErrorNegocio as e:
        db.session.rollback()
        flash(str(e), "danger")
        return redirect(volver)
    auditoria.registrar("generar_documento", current_user, "plantilla", p.id,
                        {"plantilla": p.nombre, "formato": ext, "tareas": len(ctx["tareas"])})
    db.session.commit()
    return send_file(io.BytesIO(datos), as_attachment=True, mimetype=srv.MIMES[ext],
                     download_name=srv.nombre_descarga(p, sufijo, ext))


@bp.route("/<int:plantilla_id>/tarea/<int:tarea_id>")
def tarea(plantilla_id: int, tarea_id: int):
    if not permisos.puede_ver_vista(current_user, "tareas"):
        abort(403)
    p = _plantilla(plantilla_id, "tarea")
    t = db.session.get(Tarea, tarea_id)
    if t is None or not permisos.puede_ver_tarea(current_user, t):
        abort(404)
    ctx = srv.contexto([alertas.info(t)], current_user, t.unidad)
    return _entregar(p, ctx, t.codigo, url_for("tareas.detalle", tarea_id=t.id))


def _unidad_filtrada(filtro):
    if not filtro.unidad_id.data:
        return None
    return next((u for u in permisos.unidades_visibles(current_user) if u.id == filtro.unidad_id.data), None)


def _unidad_propia():
    unidades = permisos.unidades_visibles(current_user)
    return unidades[0] if len(unidades) == 1 else None


@bp.route("/<int:plantilla_id>/listado")
def listado(plantilla_id: int):
    if not permisos.puede_ver_vista(current_user, "tareas"):
        abort(403)
    p = _plantilla(plantilla_id, "listado")
    filtro = formulario_filtros()
    infos = resumen.filtrar(resumen.cargar(current_user), filtro.data)
    ctx = srv.contexto(infos, current_user, _unidad_filtrada(filtro) or _unidad_propia(), texto_filtros(filtro))
    args = {k: v for k, v in request.args.items() if k != "formato"}
    return _entregar(p, ctx, f"{a_local(ahora_utc()):%Y%m%d}", url_for("tareas.lista", **args))


@bp.route("/<int:plantilla_id>/informe")
def informe(plantilla_id: int):
    if not permisos.puede_ver_vista(current_user, "informe"):
        abort(403)
    p = _plantilla(plantilla_id, "informe")
    filtro = formulario_filtros()
    infos = resumen.filtrar(resumen.cargar(current_user), {"unidad_id": filtro.unidad_id.data})
    criticas = [i for i in infos if i.critica]
    ctx = srv.contexto(criticas, current_user, _unidad_filtrada(filtro) or _unidad_propia())
    volver = url_for("tablero.informe", unidad_id=filtro.unidad_id.data or None)
    return _entregar(p, ctx, f"{a_local(ahora_utc()):%Y%m%d}", volver)


def _exigir_vista(vista: str) -> None:
    if not permisos.puede_ver_vista(current_user, vista):
        abort(403)


def _args(*quitar) -> dict:
    return {k: v for k, v in request.args.items() if k not in ("formato", *quitar)}


@bp.route("/<int:plantilla_id>/resumen")
def resumen_ejecutivo(plantilla_id: int):
    _exigir_vista("resumen")
    p = _plantilla(plantilla_id, "resumen")
    filtro = formulario_filtros()
    infos = resumen.cargar(current_user)
    # como la vista: los cuadros muestran todo lo visible; los filtros aplican al detalle (`tareas`)
    datos = resumen.resumen_ejecutivo(infos, permisos.unidades_visibles(current_user))
    detalle = resumen.filtrar(infos, filtro.data, solo_mre=True)
    ctx = srv.contexto_resumen(datos, detalle, current_user, _unidad_filtrada(filtro) or _unidad_propia(),
                               texto_filtros(filtro))
    return _entregar(p, ctx, f"{a_local(ahora_utc()):%Y%m%d}", url_for("tablero.resumen_ejecutivo", **_args()))


@bp.route("/<int:plantilla_id>/agenda")
def agenda_mes(plantilla_id: int):
    _exigir_vista("agenda")
    p = _plantilla(plantilla_id, "agenda")
    filtro = formulario_filtros()
    hoy = hoy_local()
    mes = agenda.leer_mes(request.args.get("mes"), hoy)
    f = {c: filtro.data[c] for c in ("unidad_id", "responsable_id")}
    infos = resumen.filtrar(resumen.cargar(current_user), f, solo_mre=permisos.solo_gestiones_mre(current_user))
    fin = agenda.mes_vecino(mes, 1)
    evs = [e for e in agenda.eventos(infos, mes, fin, hoy) if e["fecha"] < fin]
    filtros = " · ".join(x for x in texto_filtros(filtro).split(" · ") if x not in ("solo abiertas",
                                                                                   "incluye concluidas"))
    ctx = srv.contexto_agenda(mes, evs, agenda.resumen(evs, hoy), current_user,
                              _unidad_filtrada(filtro) or _unidad_propia(), filtros)
    return _entregar(p, ctx, f"{mes:%Y_%m}", url_for("agenda.mes", **_args()))


@bp.route("/<int:plantilla_id>/graficos")
def graficos(plantilla_id: int):
    from app.controllers.tablero import _datos_graficos

    _exigir_vista("graficos")
    p = _plantilla(plantilla_id, "graficos")
    filtro = formulario_filtros()
    vista, infos, datos, _, _ = _datos_graficos(filtro)
    ctx = srv.contexto_graficos(datos, infos, vista["unidades"], current_user,
                                _unidad_filtrada(filtro) or _unidad_propia())
    return _entregar(p, ctx, f"{a_local(ahora_utc()):%Y%m%d}", url_for("tablero.graficos_vista", **_args()))
