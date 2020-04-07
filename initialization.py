from blueprints.login import login_blueprint
from blueprints.webapp import webapp_blueprint
from blueprints.webapp_admin import webapp_admin_blueprint
from blueprints.webapp_api import webappapp_api_blueprint
from flask import Flask
from flask_bcrypt import Bcrypt
import flask_login


class User(flask_login.UserMixin):
    pass


app = Flask(__name__)
app.register_blueprint(login_blueprint)
app.register_blueprint(webapp_blueprint)
app.register_blueprint(webappapp_api_blueprint)
app.register_blueprint(webapp_admin_blueprint)
app.secret_key = "GamingFogKey1"

login_manager = flask_login.LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login.login"

bcrypt = Bcrypt(app)
