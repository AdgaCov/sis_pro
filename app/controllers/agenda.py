from flask import Blueprint, abort, make_response, render_template, request
from flask_login import current_user

from app.controllers.tareas import formulario_filtros
from app.extensions import db
from app.services import agenda as srv
from app.services import auditoria, pdf, permisos, resumen
from app.utils.fechas import ahora_utc, formato_fecha_hora, hoy_local

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
    desde, hasta = srv.rango_calendario(mes_)
    evs = srv.eventos(infos, desde, hasta, hoy)
    del_mes = [e for e in evs if e["fecha"].month == mes_.month]
    args = {k: v for k, v in request.args.items() if k != "mes"}
    return render_template(
        "agenda/mes.html", filtro=filtro, mes=mes_, titulo=srv.nombre_mes(mes_),
        semanas=srv.calendario(mes_, evs, hoy), dias_semana=srv.DIAS_SEMANA,
        kpis=srv.resumen(del_mes, hoy), proximos=srv.proximos(infos, 14, hoy),
        anterior=f"{srv.mes_vecino(mes_, -1):%Y-%m}", siguiente=f"{srv.mes_vecino(mes_, 1):%Y-%m}",
        actual=f"{hoy:%Y-%m}", args=args,
        ver_tareas=permisos.puede_ver_vista(current_user, "tareas"),
        varias_unidades=len(permisos.unidades_visibles(current_user)) > 1,
        solo_mre=permisos.solo_gestiones_mre(current_user),
    )


@bp.route("/agenda.pdf")
def mes_pdf():
    filtro = formulario_filtros()
    hoy = hoy_local()
    mes_ = srv.leer_mes(request.args.get("mes"), hoy)
    infos = _infos(filtro)
    fin = srv.mes_vecino(mes_, 1)
    evs = [e for e in srv.eventos(infos, mes_, fin, hoy) if e["fecha"] < fin]
    unidades = permisos.unidades_visibles(current_user)
    if filtro.unidad_id.data:
        unidades = [u for u in unidades if u.id == filtro.unidad_id.data]
    alcance = "Unidades: " + (", ".join(u.sigla for u in unidades) or "ninguna")
    if permisos.solo_gestiones_mre(current_user):
        alcance += " · solo gestiones con el MRE"
    generado = f"Generado el {formato_fecha_hora(ahora_utc())} por {current_user.nombre_usuario}"
    contenido = pdf.agenda(srv.nombre_mes(mes_), srv.por_dia(evs), srv.resumen(evs, hoy), alcance, generado)

    auditoria.registrar("descargar_pdf", current_user, "agenda", None, {"mes": f"{mes_:%Y-%m}", "eventos": len(evs)})
    db.session.commit()
    resp = make_response(contenido)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="Agenda_Despacho_{mes_:%Y_%m}.pdf"'
    resp.headers["Cache-Control"] = "no-store"
    return resp
