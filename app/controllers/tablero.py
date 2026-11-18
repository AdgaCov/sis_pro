from flask import Blueprint, abort, current_app, render_template
from flask_login import current_user

from app.controllers.tareas import formulario_filtros
from app.services import permisos, resumen

bp = Blueprint("tablero", __name__, url_prefix="/tablero")


def _exigir(vista: str) -> None:
    if not permisos.puede_ver_vista(current_user, vista):
        abort(403)


def _contexto(filtro, **extra):
    unidades = permisos.unidades_visibles(current_user)
    if filtro.unidad_id.data:
        unidades = [u for u in unidades if u.id == filtro.unidad_id.data]
    return dict(filtro=filtro, unidades=unidades, ver_tareas=permisos.puede_ver_vista(current_user, "tareas"),
                varias_unidades=len(permisos.unidades_visibles(current_user)) > 1, **extra)


@bp.route("/resumen")
def resumen_ejecutivo():
    _exigir("resumen")
    filtro = formulario_filtros()
    infos = resumen.cargar(current_user)
    ctx = _contexto(filtro)
    # Los indicadores y cuadros muestran todo lo visible; los filtros aplican al detalle
    datos = resumen.resumen_ejecutivo(infos, permisos.unidades_visibles(current_user))
    detalle = resumen.filtrar(infos, filtro.data, solo_mre=True)
    return render_template("tablero/resumen.html", datos=datos, detalle=detalle, **ctx)


@bp.route("/alertas")
def alertas():
    _exigir("alertas")
    filtro = formulario_filtros()
    f = {"unidad_id": filtro.unidad_id.data, "responsable_id": filtro.responsable_id.data, "ver_concluidas": True}
    infos = resumen.filtrar(resumen.cargar(current_user), f)
    grupos = resumen.grupos_alertas(infos, current_app.config)
    return render_template("tablero/alertas.html", grupos=grupos, **_contexto(filtro))


@bp.route("/informe")
def informe():
    _exigir("informe")
    filtro = formulario_filtros()
    ctx = _contexto(filtro)
    infos = resumen.filtrar(resumen.cargar(current_user), {"unidad_id": filtro.unidad_id.data})
    return render_template("tablero/informe.html", datos=resumen.informe_critico(infos, ctx["unidades"]), **ctx)


@bp.route("/cronograma")
def cronograma():
    _exigir("cronograma")
    filtro = formulario_filtros()
    ctx = _contexto(filtro)
    f = {c: filtro.data[c] for c in ("unidad_id", "tipo_id", "responsable_id", "ver_concluidas")}
    infos = resumen.filtrar(resumen.cargar(current_user), f)
    agrupar = ctx["varias_unidades"] and not filtro.unidad_id.data
    datos = resumen.cronograma(infos, ctx["unidades"], agrupar)
    return render_template("tablero/cronograma.html", datos=datos, **ctx)
