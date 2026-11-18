from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectMultipleField, SubmitField
from wtforms.widgets import CheckboxInput, ListWidget


class PermisoInvitadoForm(FlaskForm):
    todas_unidades = BooleanField("Todas las unidades (también las que se creen después)")
    unidades = SelectMultipleField("Unidades", coerce=int, validate_choice=False,
                                   widget=ListWidget(prefix_label=False), option_widget=CheckboxInput())
    enviar = SubmitField("Guardar")
