from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property
from fsm import deployment_initial_state, user_initial_state
from app import app
from sqlalchemy import event
from transitions import Machine
from lib.config.config_loader import load_config

bcrypt = Bcrypt(app)

app.config['SQLALCHEMY_DATABASE_URI'] = load_config().get("db").get("connection_url")
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
db = None

if __name__ == "database":
    db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    state = db.Column(db.String(120), default=user_initial_state)
    email = db.Column(db.Text, unique=True)
    _password = db.Column(db.Text)
    firstname = db.Column(db.Text)
    lastname = db.Column(db.Text)
    url_picture = db.Column(db.Text, nullable=True, default=None)

    email_confirmed = db.Column(db.Boolean, default=False)
    user_authorized = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)

    email_confirmation_token = db.Column(db.Text, nullable=True, default=None)
    admin_authorization_token = db.Column(db.Text, nullable=True, default=None)

    deployments = db.relationship('Deployment', backref='user', lazy=True)

    @hybrid_property
    def password(self):
        return self._password

    @password.setter
    def _set_password(self, plaintext):
        self._password = bcrypt.generate_password_hash(plaintext)


class Deployment(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    state = db.Column(db.String(120), default=deployment_initial_state)

    public_key = db.Column(db.Text)
    environment = db.Column(db.Text)
    duration = db.Column(db.Text)
    init_script = db.Column(db.Text)

    name = db.Column(db.Text)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)

    label = db.Column(db.Text)

    server_id = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                        nullable=False)


@event.listens_for(User, 'init')
@event.listens_for(User, 'load')
def receive_init(obj, *args, **kwargs):
    from fsm import user_initial_state, user_states, user_transitions
    # when we load data from the DB(via query) we need to set the proper initial state
    initial = obj.state or user_initial_state
    machine = Machine(model=obj, states=user_states, transitions=user_transitions, initial=initial)
    # in case that we need to have machine obj in model obj
    setattr(obj, 'machine', machine)


@event.listens_for(Deployment, 'init')
@event.listens_for(Deployment, 'load')
def receive_init(obj, *args, **kwargs):
    from fsm import deployment_initial_state, deployment_states, deployment_transitions
    # when we load data from the DB(via query) we need to set the proper initial state
    initial = obj.state or deployment_initial_state
    machine = Machine(model=obj, states=deployment_states, transitions=deployment_transitions, initial=initial)
    # in case that we need to have machine obj in model obj
    setattr(obj, 'machine', machine)
