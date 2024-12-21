from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Regexp, EqualTo
from wtforms import ValidationError
from ..models import User


class LoginForm(FlaskForm):
    email = StringField('Почта', validators=[DataRequired(), Length(1, 64),
                                             Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')


class RegistrationForm(FlaskForm):
    email = StringField('Почта', validators=[DataRequired(), Length(1, 64), Email()])
    username = StringField('Имя пользователя', validators=[
        DataRequired(), Length(1, 64),
        Regexp('^[A-Za-z][A-Za-z0-9_.]*$', 0, 
               'Usernames must have only letters, numbers, dots or underscores')])
    password = PasswordField('Пароль', validators=[
        DataRequired(), EqualTo('password2', message='Пароли должны совпадать.')])
    password2 = PasswordField('Подтвердите пароль', validators=[DataRequired()])
    phone = StringField('Телефон', validators=[DataRequired(), 
                                               Regexp(r'^\+?(\d{1,4})?(\d{10})$', 0,
                                                      'Неверный формат телефона. Например: +79991234567')])
    submit = SubmitField('Зарегистрироваться')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError('Такая почта уже существует.')

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Имя уже занято.')

    def validate_phone(self, field):
        # Проверка, если телефон уже существует в базе данных
        if User.query.filter_by(phone=field.data).first():
            raise ValidationError('Этот телефон уже зарегистрирован.')


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Старый пароль', validators=[DataRequired()])
    password = PasswordField('Новый пароль', validators=[
        DataRequired(), EqualTo('password2', message='Passwords must match.')])
    password2 = PasswordField('Подтвердите новый пароль',
                              validators=[DataRequired()])
    submit = SubmitField('Обновить пароль')


class PasswordResetRequestForm(FlaskForm):
    email = StringField('Почта', validators=[DataRequired(), Length(1, 64),
                                             Email()])
    submit = SubmitField('Обновить пароль')


class PasswordResetForm(FlaskForm):
    password = PasswordField('Новый пароль', validators=[
        DataRequired(), EqualTo('password2', message='Passwords must match')])
    password2 = PasswordField('Подтвердить пароль', validators=[DataRequired()])
    submit = SubmitField('Обновить пароль')


class ChangeEmailForm(FlaskForm):
    email = StringField('Новая почта', validators=[DataRequired(), Length(1, 64),
                                                 Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Обновить почту')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError('Почта уже существует.')
