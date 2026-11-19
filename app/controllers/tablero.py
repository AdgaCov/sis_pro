from flask import Blueprint, abort, current_app, make_response, render_template
from flask_login import current_user

from app.controllers.tareas import formulario_filtros, texto_filtros
from app.extensions import db
from app.services import agenda, auditoria, graficos, pdf, permisos, plantillas, resumen
from app.utils.fechas import a_local, ahora_utc, formato_fecha_hora, hoy_local

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
                           plantillas=plantillas.activas_para(current_user, "resumen"), **ctx)


@bp.route("/resumen.pdf")
def resumen_pdf():
    _exigir("resumen")
    filtro = formulario_filtros()
    infos = resumen.cargar(current_user)
    unidades = permisos.unidades_visibles(current_user)
    datos = resumen.resumen_ejecutivo(infos, unidades)
    detalle = resumen.filtrar(infos, filtro.data, solo_mre=True)
    alcance = "Unidades: " + (", ".join(u.sigla for u in unidades) or "ninguna")
    ahora = ahora_utc()
    generado = f"Generado el {formato_fecha_hora(ahora)} por {current_user.nombre_usuario}"
    contenido = pdf.resumen_ejecutivo(datos, detalle, alcance, "Filtros del detalle: " + texto_filtros(filtro), generado)

    auditoria.registrar("descargar_pdf", current_user, "resumen", None, {"gestiones": len(detalle)})
    db.session.commit()
    nombre = f"Resumen_Ejecutivo_MRE_{a_local(ahora):%Y%m%d}.pdf"
    resp = make_response(contenido)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


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
                           plantillas=plantillas.activas("informe"), **ctx)


@bp.route("/informe.pdf")
def informe_pdf():
    _exigir("informe")
    filtro = formulario_filtros()
    ctx = _contexto(filtro)
    infos = resumen.filtrar(resumen.cargar(current_user), {"unidad_id": filtro.unidad_id.data})
    datos = resumen.informe_critico(infos, ctx["unidades"])
    alcance = "Unidades: " + (", ".join(u.sigla for u in ctx["unidades"]) or "ninguna")
    ahora = ahora_utc()
    generado = f"Generado el {formato_fecha_hora(ahora)} por {current_user.nombre_usuario}"
    contenido = pdf.informe_critico(datos, alcance, generado)
    auditoria.registrar("descargar_pdf", current_user, "informe", None, {"criticas": datos["total"]})
    db.session.commit()
    resp = make_response(contenido)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="Informe_Critico_{a_local(ahora):%Y%m%d}.pdf"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


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
                plantillas=plantillas.activas_para(current_user, "graficos"),
                proximos=graficos.proximos_vencimientos(infos), calendario=calendario,
                titulo_mes=agenda.nombre_mes(mes), dias_semana=agenda.DIAS_SEMANA, **ctx)


@bp.route("/graficos")
def graficos_vista():
    _exigir("graficos")
    return render_template("tablero/graficos.html", **contexto_graficos(formulario_filtros()))


@bp.route("/graficos.pdf")
def graficos_pdf():
    _exigir("graficos")
    filtro = formulario_filtros()
    ctx, infos, datos, por_unidad, solo_mre = _datos_graficos(filtro)
    alcance = "Unidades: " + (", ".join(u.sigla for u in ctx["unidades"]) or "ninguna")
    if solo_mre:
        alcance += " · solo gestiones con el MRE"
    generado = f"Generado el {formato_fecha_hora(ahora_utc())} por {current_user.nombre_usuario}"
    contenido = pdf.graficos(datos, por_unidad, graficos.proximos_vencimientos(infos), alcance, generado)
    auditoria.registrar("descargar_pdf", current_user, "graficos", None, {"tareas": len(infos)})
    db.session.commit()
    resp = make_response(contenido)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="Tablero_Graficos_{a_local(ahora_utc()):%Y%m%d}.pdf"'
    resp.headers["Cache-Control"] = "no-store"
    return resp
