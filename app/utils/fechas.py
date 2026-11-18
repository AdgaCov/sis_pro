"""Fechas: en la base se guarda UTC (sin tzinfo); en pantalla, America/La_Paz y dd/mm/aaaa."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context

ZONA_DEFECTO = "America/La_Paz"


def zona():
    nombre = current_app.config.get("ZONA_HORARIA", ZONA_DEFECTO) if has_app_context() else ZONA_DEFECTO
    return ZoneInfo(nombre)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoy_local() -> date:
    return datetime.now(zona()).date()


def a_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(zona())


def formato_fecha(valor) -> str:
    if not valor:
        return ""
    if isinstance(valor, datetime):
        valor = a_local(valor)
    return valor.strftime("%d/%m/%Y")


def formato_fecha_hora(valor: datetime | None) -> str:
    if not valor:
        return ""
    return a_local(valor).strftime("%d/%m/%Y %H:%M")
