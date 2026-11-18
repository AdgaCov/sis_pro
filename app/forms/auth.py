from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length

MSG_OBLIGATORIO = "Campo obligatorio."


class LoginForm(FlaskForm):
    nombre_usuario = StringField("Usuario", validators=[DataRequired(MSG_OBLIGATORIO), Length(max=50)])
    clave = PasswordField("Contraseña", validators=[DataRequired(MSG_OBLIGATORIO), Length(max=200)])
    enviar = SubmitField("Ingresar")


class CambiarClaveForm(FlaskForm):
    actual = PasswordField("Contraseña actual", validators=[DataRequired(MSG_OBLIGATORIO)])
    nueva = PasswordField("Contraseña nueva", validators=[DataRequired(MSG_OBLIGATORIO), Length(max=200)])
    confirmar = PasswordField(
        "Repita la contraseña nueva",
        validators=[DataRequired(MSG_OBLIGATORIO), EqualTo("nueva", "Las contraseñas no coinciden.")],
    )
    enviar = SubmitField("Cambiar contraseña")
