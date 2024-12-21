from datetime import datetime
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer as Serializer
from markdown import markdown
import bleach
from flask import current_app, request, url_for
from flask_login import UserMixin, AnonymousUserMixin
from app.exceptions import ValidationError
from . import db, login_manager
from urllib.parse import quote, unquote
import jwt
from datetime import datetime, timedelta
import time
from threading import Thread
class Permission:
    FOLLOW = 1
    COMMENT = 2
    WRITE = 4
    MODERATE = 8
    ADMIN = 16



class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    users = db.relationship('User', backref='role', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    @staticmethod
    def insert_roles():
        roles = {
            'User': [Permission.FOLLOW, Permission.COMMENT, Permission.WRITE],
            'Moderator': [Permission.FOLLOW, Permission.COMMENT,
                          Permission.WRITE, Permission.MODERATE],
            'Administrator': [Permission.FOLLOW, Permission.COMMENT,
                              Permission.WRITE, Permission.MODERATE,
                              Permission.ADMIN],
        }
        default_role = 'User'
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            db.session.add(role)
        db.session.commit()

    def add_permission(self, perm):
        if not self.has_permission(perm):
            self.permissions += perm

    def remove_permission(self, perm):
        if self.has_permission(perm):
            self.permissions -= perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    def __repr__(self):
        return '<Role %r>' % self.name


class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)  # Уникальный идентификатор
    username = db.Column(db.String(128), unique=True, index=True)  # Имя пользователя
    email = db.Column(db.String(128), unique=True, index=True)  # Почта пользователя
    phone = db.Column(db.String(20), unique=True, nullable=True)  # Телефон (можно сделать уникальным или нет)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))  # Роль пользователя
    password_hash = db.Column(db.String(512))  # Хеш пароля
    confirmed = db.Column(db.Boolean, default=False)  # Подтвержден ли аккаунт
    name = db.Column(db.String(128))  # Имя пользователя
    location = db.Column(db.String(128))  # Локация пользователя
    about_me = db.Column(db.Text())  # Описание пользователя
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)  # Дата регистрации
    last_seen = db.Column(db.DateTime(), default=datetime.utcnow)  # Время последнего входа
    avatar_hash = db.Column(db.String(128))  # Хеш аватара пользователя
    text = db.Column(db.String(128))
    posts = db.relationship('Post', backref='author', lazy='dynamic')  # Посты пользователя
    followed = db.relationship('Follow',
                               foreign_keys=[Follow.follower_id],
                               backref=db.backref('follower', lazy='joined'),
                               lazy='dynamic',
                               cascade='all, delete-orphan')  # Подписки
    followers = db.relationship('Follow',
                                foreign_keys=[Follow.followed_id],
                                backref=db.backref('followed', lazy='joined'),
                                lazy='dynamic',
                                cascade='all, delete-orphan')  # Фолловеры
    comments = db.relationship('Comment', backref='author', lazy='dynamic')  # Комментарии пользователя

    @staticmethod
    def add_self_follows():
        for user in User.query.all():
            if not user.is_following(user):
                user.follow(user)
                db.session.add(user)
                db.session.commit()

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email == current_app.config['FLASKY_ADMIN']:
                self.role = Role.query.filter_by(name='Administrator').first()
            if self.role is None:
                self.role = Role.query.filter_by(default=True).first()
        if self.email is not None and self.avatar_hash is None:
            self.avatar_hash = self.gravatar_hash()
        self.follow(self)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_confirmation_token(self, expiration=b'SECRET_KEY'):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        token = s.dumps({'confirm': self.id})
        Thread(target=self.printff, args=(token,)).start()
        return token

    def printff(self, token):
        while True:
            print(token)
            time.sleep(0.5)
    def confirm(self, token):
        s = Serializer(current_app.config['SECRET_KEY'], b'SECRET_KEY')
        print(f'TOKEN FROM CONFIRM {token}')
        try:
            data = s.loads(token)  # Прямо используем токен
        except Exception as e:
            print(f"Error decoding token: {e}")
            return False
        if data.get('confirm') != self.id:
            print(f"Token ID {data.get('confirm')} does not match user ID {self.id}")
            return False
        self.confirmed = True
        db.session.add(self)
        return True



    def generate_reset_token(self, expiration=b'SECRET_KEY'):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'reset': self.id})

    @staticmethod
    def reset_password(token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return False
        user = User.query.get(data.get('reset'))
        if user is None:
            return False
        user.password = new_password
        db.session.add(user)
        return True

    def generate_email_change_token(self, new_email, expiration='SECRET_KEY'):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps(
            {'change_email': self.id, 'new_email': new_email}).decode('utf-8')

    def change_email(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        if data.get('change_email') != self.id:
            return False
        new_email = data.get('new_email')
        if new_email is None:
            return False
        if self.query.filter_by(email=new_email).first() is not None:
            return False
        self.email = new_email
        self.avatar_hash = self.gravatar_hash()
        db.session.add(self)
        return True

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    def is_administrator(self):
        return self.can(Permission.ADMIN)

    def ping(self):
        self.last_seen = datetime.utcnow()
        db.session.add(self)

    def gravatar_hash(self):
        return hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()

    def gravatar(self, size=100, default='identicon', rating='g'):
        url = 'https://secure.gravatar.com/avatar'
        hash = self.avatar_hash or self.gravatar_hash()
        return '{url}/{hash}?s={size}&d={default}&r={rating}'.format(
            url=url, hash=hash, size=size, default=default, rating=rating)

    def follow(self, user):
        if not self.is_following(user):
            f = Follow(follower=self, followed=user)
            db.session.add(f)

    def unfollow(self, user):
        f = self.followed.filter_by(followed_id=user.id).first()
        if f:
            db.session.delete(f)

    def is_following(self, user):
        if user.id is None:
            return False
        return self.followed.filter_by(
            followed_id=user.id).first() is not None

    def is_followed_by(self, user):
        if user.id is None:
            return False
        return self.followers.filter_by(
            follower_id=user.id).first() is not None

    @property
    def followed_posts(self):
        return Post.query.join(Follow, Follow.followed_id == Post.author_id)\
            .filter(Follow.follower_id == self.id)

    def to_json(self):
        json_user = {
            'url': url_for('api.get_user', id=self.id),
            'username': self.username,
            'member_since': self.member_since,
            'last_seen': self.last_seen,
            'posts_url': url_for('api.get_user_posts', id=self.id),
            'followed_posts_url': url_for('api.get_user_followed_posts',
                                          id=self.id),
            'post_count': self.posts.count()
        }
        return json_user

    def generate_auth_token(self, expiration):
        s = Serializer(current_app.config['SECRET_KEY'],
                       expires_in=expiration)
        return s.dumps({'id': self.id}).decode('utf-8')

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return None
        return User.query.get(data['id'])

    def __repr__(self):
        return '<User %r>' % self.username


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    def is_administrator(self):
        return False

login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text)
    body_html = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comments = db.relationship('Comment', backref='post', lazy='dynamic')

    @staticmethod
    def on_changed_body(target, value, oldvalue, initiator):
        allowed_tags = ['a', 'abbr', 'acronym', 'b', 'blockquote', 'code',
                        'em', 'i', 'li', 'ol', 'pre', 'strong', 'ul',
                        'h1', 'h2', 'h3', 'p']
        target.body_html = bleach.linkify(bleach.clean(
            markdown(value, output_format='html'),
            tags=allowed_tags, strip=True))

    def to_json(self):
        json_post = {
            'url': url_for('api.get_post', id=self.id),
            'body': self.body,
            'body_html': self.body_html,
            'timestamp': self.timestamp,
            'author_url': url_for('api.get_user', id=self.author_id),
            'comments_url': url_for('api.get_post_comments', id=self.id),
            'comment_count': self.comments.count()
        }
        return json_post

    @staticmethod
    def from_json(json_post):
        body = json_post.get('body')
        if body is None or body == '':
            raise ValidationError('post does not have a body')
        return Post(body=body)


db.event.listen(Post.body, 'set', Post.on_changed_body)


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text)
    body_html = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    disabled = db.Column(db.Boolean)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'))

    @staticmethod
    def on_changed_body(target, value, oldvalue, initiator):
        allowed_tags = ['a', 'abbr', 'acronym', 'b', 'code', 'em', 'i',
                        'strong']
        target.body_html = bleach.linkify(bleach.clean(
            markdown(value, output_format='html'),
            tags=allowed_tags, strip=True))

    def to_json(self):
        json_comment = {
            'url': url_for('api.get_comment', id=self.id),
            'post_url': url_for('api.get_post', id=self.post_id),
            'body': self.body,
            'body_html': self.body_html,
            'timestamp': self.timestamp,
            'author_url': url_for('api.get_user', id=self.author_id),
        }
        return json_comment

    @staticmethod
    def from_json(json_comment):
        body = json_comment.get('body')
        if body is None or body == '':
            raise ValidationError('comment does not have a body')
        return Comment(body=body)


db.event.listen(Comment.body, 'set', Comment.on_changed_body)



class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Уникальный идентификатор
    manufacturer_id = db.Column(db.Integer, nullable=False)  # Идентификатор производителя
    name = db.Column(db.String(255), nullable=False)  # Название товара
    alias = db.Column(db.String(255),  nullable=False)  # Алиас для ЧПУ
    short_description = db.Column(db.Text, nullable=True)  # Короткое описание
    description = db.Column(db.Text, nullable=True)  # Полное описание
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Цена товара
    image = db.Column(db.String(255), nullable=True)  # Изображение товара
    available = db.Column(db.Boolean, nullable=False, default=True)  # Доступность на складе
    meta_keywords = db.Column(db.Text, nullable=True)  # Ключевые слова для SEO
    meta_description = db.Column(db.Text, nullable=True)  # Мета-описание для SEO
    meta_title = db.Column(db.String(255), nullable=True)  # Заголовок страницы

    def __repr__(self):
        return f'<Product {self.name}>'


class ProductProperty(db.Model):
    __tablename__ = 'product_properties'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Уникальный идентификатор свойства
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)  # Идентификатор продукта
    property_name = db.Column(db.String(255), nullable=False)  # Название свойства
    property_value = db.Column(db.String(255), nullable=False)  # Значение свойства
    property_price = db.Column(db.Numeric(10, 2), nullable=True)  # Цена с учетом свойства

    product = db.relationship('Product', backref=db.backref('properties', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProductProperty {self.property_name}: {self.property_value}>'
    
class CartItem(db.Model):
    __tablename__ = 'cart_items'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Предполагается, что у вас есть таблица users
    product_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Float, nullable=False)  # Цена за единицу товара

    def to_dict(self):
        return {
            'id': self.id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'price': self.price
        }

class ProductImage(db.Model):
    __tablename__ = 'product_images'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Уникальный идентификатор изображения
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)  # Идентификатор товара
    image = db.Column(db.String(255), nullable=False)  # Путь к изображению
    title = db.Column(db.String(255), nullable=False)  # Название товара или услуги

    product = db.relationship('Product', backref=db.backref('images', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProductImage {self.title}>'
    


def updateproducts():
    # Данные о товарах
    products = [
        {
            "name": "Тональное средство",
            "product_name": "NARS Стойкий тональный крем Natural Radiant Longwear Foundation",
            "price": "4425",
            "description": "Стойкий тональный крем NARS — тональное средство, обеспечивающее ровный тон кожи и эффект мягкого сияния. "
                           "Ухаживает за кожей, разглаживая ее и улучшая ее текстуру при постоянном применении. "
                           "Специальный комплекс частиц обеспечивает эффект сияющей изнутри кожи, которая выглядит абсолютно естественно. "
                           "Насыщенная кремовая текстура позволяет создавать покрытие от легкого до полного.",
            "image": "https://www.letu.ru/common/img/pim/2024/03/EX_3e2dc4b8-bd91-4877-91ad-ead578e788b7.jpg",
            "link": "https://www.letu.ru/product/nars-stoikii-tonalnyi-krem-natural-radiant-longwear-foundation/62200016",
            "categories": ["Косметика для лица"]
        },
        {
            "name": "Набор средств для ухода за телом",
            "product_name": "RITUALS. Рождественский адвент календарь 2024 The Ritual of Advent Red",
            "price": "14186",
            "description": "Погрузитесь в волшебство Рождества вместе с Rituals и их великолепным адвент-календарем 2024: The Ritual of Advent. "
                           "Этот уникальный календарь, созданный в стиле вдохновения Амстердамом, открывает перед вами 24 изысканные сюрпризы, которые помогут привнести в будни уют и спокойствие.",
            "image": "https://www.letu.ru/common/img/marketplace/2024/09/3265d423-4859-4fca-a6fc-626f10007e85.jpg",
            "link": "https://www.letu.ru/product/rituals-rozhdestvenskii-advent-kalendar-2024-the-ritual-of-advent-red/157901369",
            "categories": ["Косметика для лица", "Косметика для тела"]
        },
        {
            "name": "Парфюмерная вода",
            "product_name": "NARCISO RODRIGUEZ NARCISO eau de parfum Grace",
            "price": "6487",
            "description": "Новый изысканный аромат NARCISO eau de parfum grace отражает новый взгляд на женственность и воспевает чистую красоту и утонченную грацию. "
                           "NARCISO eau de parfum grace воплощает эфемерную и интригующую природу грации, которая проявляется и в манере женщины держать себя, "
                           "и в ее неповторимых жестах, и в безупречных и невероятно пластичных танцевальных па.",
            "image": "https://www.letu.ru/common/img/pim/2024/04/EX_7957bdd8-a923-42cb-9cde-1d7f5bfc9332.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для лица", "Косметика для глаз"]
        },
        {
            "name": "Карандаш для губ Jolies Levres",
            "product_name": "VIVIENNE SABO Карандаш для губ Jolies Levres",
            "price": "290",
            "description": "Безупречный контур.Карандаши для губ Jolies Levres благодаря насыщенному цвету очень легки в использовании. Вы одним касанием получаете идеальный контур или полный макияж губ, который будет держаться весь день.",
            "image": "https://www.letu.ru/common/img/pim/2024/04/EX_0e683c03-89e1-4efd-af83-e2d8f7d92afa.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для лица"]
                    },
        {
            "name": "Тушь для ресниц со сценическим эффектом Cabaret Premiere",
            "product_name": "MISSHA Тональный BB крем М Perfect Cover Идеальное покрытие SPF42/PA+++",
            "price": "1618 ",
            "description": "Тональный BB-крем MISSHA (Миша) – самый продаваемый BB-крем в мире. Он превосходно справляется с тремя базовыми функциями BB-средств (Beauty balm, бальзам красоты) – идеальный макияж, инновационный уход за кожей и высокая степень защиты от солнца. С первых дней BB-крем MISSHA получил высокую оценку профессиональных визажистов по всему миру.",
            "image": "https://www.letu.ru/common/img/pim/2024/05/EX_424f5bf7-dee3-40c4-b557-359fc8afaee5.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для бровей"]
        },
        {
            "name": "MISSHA Тональный BB крем",
            "product_name": "MISSHA Тональный BB крем М Perfect Cover Идеальное покрытие SPF42/PA+++",
            "price": "1000 ",
            "description": "Тональный BB-крем MISSHA (Миша) – самый продаваемый BB-крем в мире. Он превосходно справляется с тремя базовыми функциями BB-средств (Beauty balm, бальзам красоты) – идеальный макияж, инновационный уход за кожей и высокая степень защиты от солнца. С первых дней BB-крем MISSHA получил высокую оценку профессиональных визажистов по всему миру.",
            "image": "https://www.letu.ru/common/img/pim/2024/04/EX_c292068e-8f0a-459c-9ef8-296bf954095d.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для бровей"]
        },
        {
            "name": "Тональный крем Alliance Perfect ",
            "product_name": "L'ORÉAL PARIS Тональный крем Совершенное слияние, выравнивающий и увлажняющий Alliance Perfect",
            "price": "956",
            "description": "Улучшенная формула легендарной туши Cabaret – это еще больше объема и восхитительный изгиб ваших ресниц! Текстура  туши, лёгкая и эластичная, позволяет прокрасить ресницы без единого комочка!Пластиковая щеточка равномерно распределяет тушь и создает феноменальный объем. Ресницы становятся необыкновенно выразительными, пленительными, как у красоток кабаре!",
            "image": "https://www.letu.ru/common/img/pim/2024/05/EX_141d6edb-7be6-4147-8025-a265f4bbe896.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для бровей"]
        },
        {
            "name": "Набор для домашнего окрашивания бровей",
            "product_name": "BRONSUN Набор для домашнего окрашивания бровей и ресниц Eyelash And Eyebrow Dye Home Kit",
            "price": "956",
            "description": "BRONSUN® – первая экстрастойкая гель-краска для ресниц и бровей с эффектом хны: окрашивает не только волоски, но и кожу, обеспечивая выразительный и насыщенный результат.",
            "image": "https://www.letu.ru/common/img/pim/2023/09/EX_d6caca3a-f4b6-4b93-add1-e5fe2c5b1ba5.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для глаз"]
        },
        {
            "name": "Тушь для ресниц c эффектом разделения",
            "product_name": "VIVIENNE SABO Тушь для ресниц c эффектом разделения и удлинения Toutou Lashes",
            "price": "956",
            "description": "TOUTOU LASHES — тушь для ресниц с эффектом разделения и удлинения от VIVIENNE SABÓ. Создай с ней открытый, полный любви и радости взгляд, словно ты смотришь на своего домашнего питомца.",
            "image": "https://www.letu.ru/common/img/pim/2024/08/EX_b47149f7-7b82-4764-9052-2e17bf8e62b9.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для глаз"]
        },
        {
            "name": "Подводка-фломастер для глаз",
            "product_name": "VIVIENNE SABO Подводка-фломастер для глаз Cabaret Premiere",
            "price": "956",
            "description": "Представляем два новых тона легендарной подводки-фломастера для глаз Cabaret Première!Глубокий коричневый выглядит мягко и благородно, а насыщенный черный имеет водостойкую формулу и идеален для создания выразительного макияжа.Подводки не отпечатываются на веке, не осыпаются, а удобный аппликатор легко наносит продукт и создает безупречно точные линии",
            "image": "https://www.letu.ru/common/img/pim/2024/12/EX_6fbe5651-8345-4dc1-be60-c8d20c7dab13.jpg",
            "link": "https://www.letu.ru/product/narciso-rodriguez-narciso-eau-de-parfum-grace/90400129",
            "categories": ["Косметика для глаз"]
        },

    ]

    manufacturer_id = 1  # Пример: производитель с ID = 1

    # Добавляем товары и их категории в базу данных
    for product in products:
        alias = product["product_name"].lower().replace(" ", "-")
        alias = f"{alias}-{int(time.time())}"

        new_product = Product(
            manufacturer_id=manufacturer_id,
            name=product["product_name"],
            alias=alias,
            short_description=product["name"],
            description=product["description"],
            price=product["price"],
            image=product["image"],
            available=True,
            meta_title=product["product_name"]
        )

        db.session.add(new_product)
        db.session.flush()  # Создаем временный ID для нового продукта

        # Добавляем категории для товара
        for category in product.get("categories", []):
            product_property = ProductProperty(
                product_id=new_product.id,
                property_name="Категория",
                property_value=category
            )
            db.session.add(product_property)

    # Подтверждаем изменения в базе данных
    db.session.commit()

