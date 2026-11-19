from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from app.controllers.tablero import contexto_graficos
from app.controllers.tareas import formulario_filtros
from app.services import permisos

bp = Blueprint("inicio", __name__)

ENLACES = {
    "tareas": ("tareas.lista", "Tareas", "Registrar y actualizar tareas"),
    "resumen": ("tablero.resumen_ejecutivo", "Resumen ejecutivo", "Gestiones con el MRE por unidad, instancia y tipo"),
    "alertas": ("tablero.alertas", "Alertas", "Lo que requiere atención"),
    "informe": ("tablero.informe", "Informe crítico", "Tareas críticas y su línea de solución"),
    "cronograma": ("tablero.cronograma", "Cronograma", "Plazos y subtareas en el tiempo"),
    "agenda": ("agenda.mes", "Agenda Despacho", "Fechas límite y recordatorios del mes"),
    "graficos": ("tablero.graficos_vista", "Gráficos", "El tablero en pantalla completa y en PDF"),
}


@bp.route("/")
def index():
    """Dashboard: los gráficos del tablero (con filtro por unidad) y los accesos a cada vista."""
    if current_user.es_invitado:
        return redirect(url_for("tablero.resumen_ejecutivo"))
    vistas = [v for v in ENLACES if permisos.puede_ver_vista(current_user, v)]
    unidades = permisos.unidades_visibles(current_user)
    ctx = contexto_graficos(formulario_filtros()) if unidades and "graficos" in vistas else {}
    return render_template("inicio.html", vistas=vistas, unidades_usuario=unidades,
                           enlaces=[ENLACES[v] for v in vistas], **ctx)
