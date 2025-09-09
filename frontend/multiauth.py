from functools import wraps
from flask import session, abort, redirect, request, url_for, has_request_context, render_template
from utils import *
from main import app
from main import multipass
from werkzeug.local import LocalProxy
from werkzeug.security import check_password_hash
from flask_multipass.providers.static import StaticAuthProvider
from flask_multipass.data import AuthInfo
from flask_multipass.exceptions import InvalidCredentials
from flask_multipass.providers.sqlalchemy import SQLAlchemyAuthProviderBase, SQLAlchemyIdentityProviderBase
from flask_sqlalchemy import SQLAlchemy
from passlib.hash import scrypt
import re

db = SQLAlchemy()

class Permission(db.Model):
    __tablename__ = 'permissions'
    __table_args__ = (
        db.UniqueConstraint('dataset_id', 'user_id'),
      )

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.String(80))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship("User", backref=db.backref("user", uselist=False))

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String)
    affiliation = db.Column(db.String)
    admin = db.Column(db.Boolean, db.ColumnDefault(False))
    active = db.Column(db.Boolean, db.ColumnDefault(False))
    permissions = db.relationship(Permission, backref='permissions', lazy='dynamic')


    def is_admin(self):
        return self.admin

    def is_active(self):
        return self.active

    def editable_password(self):
        return False

    def can_read(self, dataset):
        if self.is_admin() or self.permissions.filter_by(dataset_id=dataset).count():
            return True
        return False

    def __repr__(self):
        return self.name

class Dataset(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(db.String, primary_key=True)
    validated = db.Column(db.Boolean, db.ColumnDefault(False))

class Identity(db.Model):
    __tablename__ = 'identities'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    provider = db.Column(db.String)
    identifier = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String)
    multipass_data = db.Column(db.Text)
    user = db.relationship(User, backref='identities')

    @property
    def provider_impl(self):
        return multipass.identity_providers[self.provider]

class LocalAuthProvider(SQLAlchemyAuthProviderBase):
    identity_model = Identity
    provider_column = Identity.provider
    identifier_column = Identity.identifier

    def check_password(self, identity, password):
        return password and scrypt.verify(password, identity.password)    

class IdentityProvider(SQLAlchemyIdentityProviderBase):
    user_model = User
    identity_user_relationship = Identity.user

# login decorator
def login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if "identifier" not in session:
            return redirect(url_for("login", provider="local"))
        # flask 1.x compatibility
        # current_app.ensure_sync is only available in Flask >= 2.0
        if callable(getattr(app, "ensure_sync", None)):
            return app.ensure_sync(func)(*args, **kwargs)
        return func(*args, **kwargs)

    return decorated_view

# handle post login
@multipass.identity_handler
def identity_handler(identity_info):
    identity = Identity.query.filter_by(identifier=identity_info.identifier, provider=identity_info.provider.name).first()
    if not identity:
        identity = Identity(provider=identity_info.provider.name, identifier=identity_info.identifier)
        db.session.add(identity)
    if not identity.user:
        user_data = identity_info.data.to_dict()        
        if identity_info.provider.name == "cnr":
            user_data["affiliation"] = "National Research Council"
            
        if identity_info.provider.name == "orcid":
            user_data["name"] = user_data["first_name"]+" "+user_data["surname"]
            user_data.pop("first_name")
            user_data.pop("surname")
     
        user_data = {"name":f"{identity_info.identifier}@{identity_info.provider.name}"} |user_data
        user_data = {k:v for k,v in user_data.items() if k in ['email', 'name', 'affiliation']}
        user = User(**user_data)
        db.session.add(user)
        user.identities.append(identity)
    session['identifier'] = identity_info.identifier
    session['provider'] = identity_info.provider.name
    db.session.commit()

# handle logout
@app.route(f"{URL_PATH}/logout")
def logout():
  return multipass.logout(url_for('index'), clear_session=True)


multipass.register_provider(LocalAuthProvider, 'localdb')
multipass.register_provider(IdentityProvider, 'localdb')

# current user
current_user = LocalProxy(lambda: _get_user())

def _get_user():
    if has_request_context():
        if "identifier" in session:
            # identity_info.provider.get_identity_groups(identity_info.identifier)
            return Identity.query.filter_by(identifier=session["identifier"], provider=session["provider"]).first().user

    return None

def _user_context_processor():
    return dict(current_user=_get_user())

app.context_processor(_user_context_processor)

def load_and_authorize_dataset(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        dataset = get_dataset(clean_user_input(request.args.get('id') or request.form.get('id') or request.json.get('id')), current_user)
        dataset.validated = get_dataset_validity(dataset.id)
        if not dataset:
            abort(401)
        return f(dataset, *args, **kwargs)
    return wrapper

def load_and_authorize_datasets(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        datasets = get_datasets_list(current_user)
        for dataset in datasets:
            dataset.validated = get_dataset_validity(dataset.id)
            dataset.users = [x.user for x in get_dataset_permissions(dataset.id)]
        return f(datasets, *args, **kwargs)
    return wrapper

# login decorator


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            abort(401, "This operation required admin permissions!")
        return f(*args, **kwargs)

    return wrapper

def active_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_active():
            abort(401, "Your account needs to be activated by admin.")
        return f(*args, **kwargs)

    return wrapper    

def add_user_to_dataset(user_id, dataset_id):
    u = User.query.filter_by(id=user_id).first()
    permission = Permission(dataset_id=dataset_id)
    u.permissions.append(permission)
    db.session.add(u)
    db.session.commit()
    
def remove_user_from_dataset(user_id, dataset_id):
    permission = Permission.query.filter_by(user_id=user_id, dataset_id=dataset_id).first()
    db.session.delete(permission)
    db.session.commit()

def get_dataset_permissions(dataset_id):
    permissions = Permission.query.filter_by(dataset_id=dataset_id)
    db.session.commit()    
    return permissions

def get_dataset_validity(dataset_id):
    dataset = Dataset.query.filter_by(id=dataset_id).first()
    if not dataset:
        dataset = Dataset(id=dataset_id)
        db.session.add(dataset)
    db.session.commit()
    return dataset.validated

def set_dataset_validity(dataset_id, validated):
    dataset = Dataset.query.filter_by(id=dataset_id).first()
    if not dataset:
        dataset = Dataset(id=dataset_id)
        db.session.add(dataset)
    dataset.validated = validated
    db.session.commit()

def add_user(name, email, password, affiliation, captcha_result):
    if email == "":
        return "Empty email", None
    if not re.match(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', email):
        return "Email is not valid", None
    if affiliation == "":
        return "Empty affiliation", None
    if len(password) < 6:
        return "Password too short", None
    if captcha_result == False:
        return "Failed captcha, retry", None
    
    if Identity.query.filter_by(provider='local', identifier=email).count():
        return 'User with this email already exists. Please choose a different email.', None
    user = User(name=name, email=email, affiliation=affiliation)
    identity = Identity(provider='local', identifier=email, multipass_data='null', password=scrypt.hash(password))
    user.identities.append(identity)
    db.session.add(user)
    db.session.commit()
    return "ok", user

def delete_user(id):
    user = User.query.filter_by(id=id).first()
    if not user:
        return False
    db.session.delete(user)
    db.session.commit()
    return True

def get_users():
    return User.query.all()

def get_user(id):
    return User.query.filter_by(id=id).first()


def get_user_provider(id):
    identity=Identity.query.filter_by(user_id=id).first()
    return identity.provider    

def update_user(user, new_password):
    if user.name == "":
        return "Empty name"
    if user.email == "":
        return "Empty email"
    if not re.match(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', user.email):
        return "Email is not valid"
    if user.affiliation == "":
        return "Empty affiliation"
    
    if new_password:
        if len(new_password) < 6:
            return "Password too short"
        new_password = scrypt.hash(new_password)
        for user_local_identity in Identity.query.filter_by(user_id=user.id, provider='local'):
            user_local_identity.password = new_password 

    # db.session.update(user)
    db.session.commit()
    return "ok"

def delete_dataset_permissions(dataset_id):
    for permission in Permission.query.filter_by(dataset_id=dataset_id).all():
        db.session.delete(permission)
    db.session.commit()

multipass.init_app(app)
db.init_app(app)
with app.app_context():
    db.create_all()
    if not User.query.filter_by(name='admin').count():
        user = User(name='admin', email='test@example.com', affiliation='CNR', admin=True, active=True)
        identity = Identity(provider='local', identifier='admin', multipass_data='null')
        identity.password = scrypt.hash('admin')
        user.identities.append(identity)
        db.session.add(user)
        db.session.commit()
