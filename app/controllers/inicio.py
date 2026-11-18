from flask import Blueprint, render_template
from flask_login import current_user

from app.models.permiso_invitado import VISTAS_INVITADO
from app.services import permisos

bp = Blueprint("inicio", __name__)


@bp.route("/")
def index():
    vistas = [v for v in VISTAS_INVITADO if permisos.puede_ver_vista(current_user, v)]
    unidades = permisos.unidades_visibles(current_user)
    return render_template("inicio.html", vistas=vistas, unidades=unidades)
