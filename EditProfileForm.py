from flask_wtf import FlaskForm
from wtforms import StringField, FileField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed

class EditProfileForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    avatar = FileField('Аватарка', validators=[FileAllowed(['jpg', 'png', 'jpeg'], 'Только изображения')])
    submit = SubmitField('Сохранить')