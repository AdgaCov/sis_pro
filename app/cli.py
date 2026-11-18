import click
from flask import Flask

from app import datos_iniciales as datos
from app.extensions import db
from app.models import Cargo, Catalogo, Unidad
from app.models.usuario import ROL_ADMIN
from app.services import ErrorNegocio
from app.services import usuarios as srv


def cargar_catalogos() -> dict:
    """Carga unidades, cargos y catálogos. Se puede repetir: solo agrega lo que falta."""
    res = {"unidades": 0, "cargos": 0, "catalogos": 0}

    unidades = {}
    for orden, (sigla, nombre) in enumerate(datos.UNIDADES, start=1):
        u = Unidad.query.filter_by(sigla=sigla).first()
        if u is None:
            u = Unidad(sigla=sigla, nombre=nombre, orden=orden, activa=True, ultimo_correlativo=0)
            db.session.add(u)
            res["unidades"] += 1
        unidades[sigla] = u
    db.session.flush()

    for sigla, cargos in datos.CARGOS_INICIALES.items():
        existentes = {c.nombre.upper() for c in Cargo.query.filter_by(unidad_id=unidades[sigla].id)}
        for nombre in cargos + [datos.CARGO_APOYO]:
            if nombre.upper() not in existentes:
                db.session.add(Cargo(unidad_id=unidades[sigla].id, nombre=nombre,
                                     es_apoyo=nombre == datos.CARGO_APOYO, activo=True))
                res["cargos"] += 1

    for tipo, valores in datos.CATALOGOS.items():
        existentes = {c.valor: c for c in Catalogo.query.filter_by(tipo=tipo)}
        for orden, valor in enumerate(valores, start=1):
            protegido = (tipo, valor) in datos.PROTEGIDOS
            c = existentes.get(valor)
            if c is None:
                db.session.add(Catalogo(tipo=tipo, valor=valor, orden=orden, activo=True, protegido=protegido))
                res["catalogos"] += 1
            elif protegido and not (c.protegido and c.activo):
                c.protegido, c.activo = True, True
    db.session.commit()
    return res


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("crear-admin")
    @click.option("--usuario", prompt="Usuario", help="Nombre de usuario del administrador.")
    @click.option("--nombre", prompt="Nombre completo", help="Nombre completo.")
    @click.option("--clave", prompt="Contraseña", hide_input=True, confirmation_prompt="Repita la contraseña",
                  help="Mínimo 8 caracteres, con letras y números.")
    def crear_admin(usuario, nombre, clave):
        """Crea un usuario administrador (Planificación)."""
        try:
            u, _ = srv.crear_usuario(usuario, nombre, ROL_ADMIN, None, None, clave=clave, debe_cambiar=False)
        except ErrorNegocio as e:
            raise click.ClickException(str(e))
        click.echo(f"Administrador «{u.nombre_usuario}» creado.")

    @app.cli.command("cargar-catalogos")
    def cargar_catalogos_cmd():
        """Carga unidades, cargos iniciales (más «Apoyo») y catálogos. Se puede repetir."""
        r = cargar_catalogos()
        click.echo(f"Nuevos: {r['unidades']} unidades, {r['cargos']} cargos, {r['catalogos']} valores de catálogo.")
