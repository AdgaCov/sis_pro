from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length

from app.models.usuario import NOMBRES_ROL, ROLES


class EditarUsuarioForm(FlaskForm):
    nombre_completo = StringField("Nombre completo", validators=[DataRequired("Campo obligatorio."), Length(max=150)])
    rol = SelectField("Rol", choices=[(r, NOMBRES_ROL[r]) for r in ROLES])
    unidad_id = SelectField("Unidad", coerce=int)
    enviar = SubmitField("Guardar")

    def cargar_unidades(self, unidades) -> None:
        self.unidad_id.choices = [(0, "— Sin unidad —")] + [(u.id, f"{u.sigla} · {u.nombre}") for u in unidades]


class NuevoUsuarioForm(EditarUsuarioForm):
    nombre_usuario = StringField("Usuario", validators=[DataRequired("Campo obligatorio."), Length(min=3, max=50)])
    clave = PasswordField("Contraseña", validators=[DataRequired("Campo obligatorio."), Length(max=200)])
    confirmar = PasswordField(
        "Repita la contraseña",
        validators=[DataRequired("Campo obligatorio."), EqualTo("clave", "Las contraseñas no coinciden.")],
    )
    debe_cambiar = BooleanField("Pedir que la cambie al ingresar por primera vez", default=False)


class AccionForm(FlaskForm):
    """Formulario vacío: solo lleva el token CSRF de los botones de acción."""
