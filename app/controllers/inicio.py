from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from app.services import permisos, resumen

bp = Blueprint("inicio", __name__)

ENLACES = {
    "tareas": ("tareas.lista", "Tareas", "Registrar y actualizar tareas"),
    "resumen": ("tablero.resumen_ejecutivo", "Resumen ejecutivo", "Gestiones con el MRE por unidad, instancia y tipo"),
    "alertas": ("tablero.alertas", "Alertas", "Lo que requiere atención"),
    "informe": ("tablero.informe", "Informe crítico", "Tareas críticas y su línea de solución"),
    "cronograma": ("tablero.cronograma", "Cronograma", "Plazos y subtareas en el tiempo"),
}


@bp.route("/")
def index():
    if current_user.es_invitado:
        return redirect(url_for("tablero.resumen_ejecutivo"))
    vistas = [v for v in ENLACES if permisos.puede_ver_vista(current_user, v)]
    unidades = permisos.unidades_visibles(current_user)
    kpis = resumen.kpis_generales(resumen.cargar(current_user)) if unidades else []
    return render_template("inicio.html", vistas=vistas, unidades=unidades, kpis=kpis,
                           enlaces=[ENLACES[v] for v in vistas])
