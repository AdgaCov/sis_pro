from flask import Blueprint, abort, render_template, request
from flask_login import current_user

from app.controllers.documentos import descargar_pdf
from app.controllers.tareas import formulario_filtros
from app.services import agenda as srv
from app.services import permisos, resumen
from app.services.plantillas import vigente_para
from app.utils.fechas import hoy_local

bp = Blueprint("agenda", __name__, url_prefix="/agenda")


@bp.before_request
def _vista_permitida():
    if current_user.is_authenticated and not permisos.puede_ver_vista(current_user, "agenda"):
        abort(403)


def _infos(filtro):
    f = {c: filtro.data[c] for c in ("unidad_id", "responsable_id")}
    return resumen.filtrar(resumen.cargar(current_user), f, solo_mre=permisos.solo_gestiones_mre(current_user))


@bp.route("")
def mes():
    filtro = formulario_filtros()
    hoy = hoy_local()
    mes_ = srv.leer_mes(request.args.get("mes"), hoy)
    infos = _infos(filtro)
    # En pantalla: mes anterior, el elegido (al centro) y el siguiente
    meses = [srv.mes_vecino(mes_, d) for d in (-1, 0, 1)]
    desde, hasta = srv.rango_calendario(meses[0])[0], srv.rango_calendario(meses[-1])[1]
    evs = srv.eventos(infos, desde, hasta, hoy)
    calendarios = [srv.mes_en_pantalla(m, evs, hoy, elegido=m == mes_) for m in meses]
    del_mes = [e for e in evs if (e["fecha"].year, e["fecha"].month) == (mes_.year, mes_.month)]
    args = {k: v for k, v in request.args.items() if k != "mes"}
    return render_template(
        "agenda/mes.html", filtro=filtro, mes=mes_, titulo=srv.nombre_mes(mes_),
        calendarios=calendarios, dias_semana=srv.DIAS_SEMANA,
        kpis=srv.resumen(del_mes, hoy), proximos=srv.proximos(infos, 14, hoy),
        anterior=f"{srv.mes_vecino(mes_, -1):%Y-%m}", siguiente=f"{srv.mes_vecino(mes_, 1):%Y-%m}",
        actual=f"{hoy:%Y-%m}", args=args,
        ver_tareas=permisos.puede_ver_vista(current_user, "tareas"),
        varias_unidades=len(permisos.unidades_visibles(current_user)) > 1,
        solo_mre=permisos.solo_gestiones_mre(current_user),
        plantilla_pdf=vigente_para("agenda"),
    )


@bp.route("/agenda.pdf")
def mes_pdf():
    """La plantilla de la agenda que subió el admin, en PDF (mes y filtros de la pantalla)."""
    return descargar_pdf("agenda", "documentos.agenda_mes", "agenda.mes")
