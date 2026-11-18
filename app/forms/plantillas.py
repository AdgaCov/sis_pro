from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length

from app.models.plantilla import ALCANCES, NOMBRES_ALCANCE


class PlantillaForm(FlaskForm):
    nombre = StringField("Nombre", validators=[DataRequired("Escriba un nombre."), Length(max=150)])
    descripcion = TextAreaField("Descripción (opcional)")
    alcance = SelectField("Alcance", choices=[(a, NOMBRES_ALCANCE[a]) for a in ALCANCES])
    archivo = FileField("Archivo .docx o .xlsx")
    enviar = SubmitField("Guardar")
