from app.extensions import db
from app.models import Auditoria


def registrar(accion: str, usuario=None, entidad: str | None = None, entidad_id=None, detalle=None) -> None:
    """Agrega un registro a la sesión actual; lo confirma quien llama."""
    db.session.add(
        Auditoria(
            usuario_id=getattr(usuario, "id", None),
            accion=accion,
            entidad=entidad,
            entidad_id=None if entidad_id is None else str(entidad_id),
            detalle=detalle,
        )
    )
