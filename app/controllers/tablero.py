from flask import Blueprint, abort, current_app, render_template
from flask_login import current_user

from app.controllers.documentos import descargar_pdf
from app.controllers.tareas import formulario_filtros
from app.services import agenda, graficos, permisos, resumen
from app.services.plantillas import vigente_para
from app.utils.fechas import hoy_local

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
    return render_template("tablero/resumen.html", datos=datos, detalle=detalle,
                           plantilla_pdf=vigente_para("resumen"), **ctx)


@bp.route("/resumen.pdf")
def resumen_pdf():
    """La plantilla que subió el admin, en PDF."""
    _exigir("resumen")
    return descargar_pdf("resumen", "documentos.resumen_ejecutivo", "tablero.resumen_ejecutivo")


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
    return render_template("tablero/informe.html", datos=resumen.informe_critico(infos, ctx["unidades"]),
                           plantilla_pdf=vigente_para("informe"), **ctx)


@bp.route("/informe.pdf")
def informe_pdf():
    """La plantilla que subió el admin, en PDF."""
    _exigir("informe")
    return descargar_pdf("informe", "documentos.informe", "tablero.informe")


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


# ------------------------------------------------------------------ gráficos
def _datos_graficos(filtro):
    ctx = _contexto(filtro)
    solo_mre = permisos.solo_gestiones_mre(current_user)
    infos = resumen.filtrar(resumen.cargar(current_user), {"unidad_id": filtro.unidad_id.data, "ver_concluidas": True},
                            solo_mre=solo_mre)
    por_unidad = ctx["varias_unidades"] and not filtro.unidad_id.data
    datos = graficos.datos(infos, ctx["unidades"], por_unidad, current_app.config["META_CUMPLIMIENTO"])
    return ctx, infos, datos, por_unidad, solo_mre


def contexto_graficos(filtro) -> dict:
    """Todo lo que necesita el parcial tablero/_graficos.html (lo usan esta vista y el inicio)."""
    ctx, infos, datos, por_unidad, solo_mre = _datos_graficos(filtro)
    hoy = hoy_local()
    mes = hoy.replace(day=1)
    desde, hasta = agenda.rango_calendario(mes)
    calendario = agenda.calendario(mes, agenda.eventos(infos, desde, hasta, hoy), hoy)
    return dict(datos=datos, por_unidad=por_unidad, solo_mre=solo_mre,
                plantilla_pdf=vigente_para("graficos"),
                proximos=graficos.proximos_vencimientos(infos), calendario=calendario,
                titulo_mes=agenda.nombre_mes(mes), dias_semana=agenda.DIAS_SEMANA, **ctx)


@bp.route("/graficos")
def graficos_vista():
    _exigir("graficos")
    return render_template("tablero/graficos.html", **contexto_graficos(formulario_filtros()))


@bp.route("/graficos.pdf")
def graficos_pdf():
    """La plantilla que subió el admin, en PDF."""
    _exigir("graficos")
    return descargar_pdf("graficos", "documentos.graficos", "tablero.graficos_vista")
