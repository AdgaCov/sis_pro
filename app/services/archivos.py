"""Archivos de respaldo (adjuntos) en storage/respaldos/<unidad>/<tarea>/."""
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Adjunto, Tarea, Usuario
from app.services import ErrorNegocio, auditoria, permisos
from app.utils.fechas import ahora_utc

MAX_ADJUNTOS_POR_TAREA = 30


def raiz_respaldos() -> Path:
    return (current_app.config["STORAGE_DIR"] / "respaldos").resolve()


def ruta_absoluta(adjunto: Adjunto) -> Path:
    """Ruta en disco, comprobando que no salga de storage/respaldos."""
    raiz = raiz_respaldos()
    ruta = (raiz / adjunto.ruta_relativa).resolve()
    if raiz not in ruta.parents:
        raise ErrorNegocio("Ruta de archivo no válida.")
    return ruta


def _extension(nombre: str) -> str:
    return Path(nombre).suffix.lower().lstrip(".")


def guardar_adjunto(usuario: Usuario, tarea: Tarea, archivo) -> Adjunto:
    """`archivo` es un FileStorage de Werkzeug."""
    if not permisos.puede_editar_tarea(usuario, tarea):
        raise ErrorNegocio("No tiene permiso para adjuntar archivos a esta tarea.")
    if archivo is None or not archivo.filename:
        raise ErrorNegocio("Seleccione un archivo.")
    if len(tarea.adjuntos) >= MAX_ADJUNTOS_POR_TAREA:
        raise ErrorNegocio(f"Máximo {MAX_ADJUNTOS_POR_TAREA} archivos por tarea.")

    nombre_original = Path(archivo.filename.replace("\\", "/")).name.strip()[:255] or "respaldo"
    ext = _extension(nombre_original)
    permitidas = current_app.config["EXTENSIONES_ADJUNTO"]
    if ext not in permitidas:
        raise ErrorNegocio("Tipo de archivo no permitido. Se aceptan: " + ", ".join(sorted(permitidas)) + ".")

    max_bytes = current_app.config["MAX_MB_ADJUNTO"] * 1024 * 1024
    datos = archivo.stream.read(max_bytes + 1)
    if not datos:
        raise ErrorNegocio("El archivo está vacío.")
    if len(datos) > max_bytes:
        raise ErrorNegocio(f"El archivo supera {current_app.config['MAX_MB_ADJUNTO']} MB.")

    seguro = secure_filename(nombre_original) or f"archivo.{ext}"
    relativa = Path(tarea.unidad.sigla) / str(tarea.id) / f"{uuid.uuid4().hex[:12]}_{seguro}"
    destino = raiz_respaldos() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)

    adjunto = Adjunto(
        tarea_id=tarea.id, nombre_original=nombre_original, ruta_relativa=relativa.as_posix(),
        tamano=len(datos), tipo_mime=(archivo.mimetype or "application/octet-stream")[:150],
        subido_por_id=usuario.id, subido_en=ahora_utc(),
    )
    db.session.add(adjunto)
    tarea.actualizado_en = ahora_utc()
    tarea.actualizado_por_id = usuario.id
    db.session.flush()
    auditoria.registrar("subir_adjunto", usuario, "tarea", tarea.id,
                        {"codigo": tarea.codigo, "archivo": nombre_original, "tamano": len(datos)})
    try:
        db.session.commit()
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return adjunto


def quitar_adjunto(usuario: Usuario, tarea: Tarea, adjunto: Adjunto) -> None:
    if not permisos.puede_editar_tarea(usuario, tarea):
        raise ErrorNegocio("No tiene permiso para quitar archivos de esta tarea.")
    if adjunto.tarea_id != tarea.id:
        raise ErrorNegocio("El archivo no pertenece a esta tarea.")
    ruta = ruta_absoluta(adjunto)
    auditoria.registrar("quitar_adjunto", usuario, "tarea", tarea.id,
                        {"codigo": tarea.codigo, "archivo": adjunto.nombre_original})
    db.session.delete(adjunto)
    tarea.actualizado_en = ahora_utc()
    tarea.actualizado_por_id = usuario.id
    db.session.commit()
    try:
        ruta.unlink(missing_ok=True)
    except OSError:  # p. ej. en Windows, si alguien lo está descargando en este momento
        current_app.logger.warning("No se pudo borrar el archivo %s", ruta)
