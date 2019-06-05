import flask_login
from flask import Flask
import datetime
from blueprints.login import login_blueprint
from blueprints.webapp import webapp_blueprint
from blueprints.switch_api import switch_api_blueprint
from blueprints.webapp_api import webappapp_api_blueprint

login_manager = flask_login.LoginManager()

app = Flask(__name__)
app.register_blueprint(login_blueprint)
app.register_blueprint(webapp_blueprint)
app.register_blueprint(switch_api_blueprint)
app.register_blueprint(webappapp_api_blueprint)

app.secret_key = "GamingFogKey1"
# USE_SESSION_FOR_NEXT = True

login_manager.init_app(app)
login_manager.login_view = "login.login"


@login_manager.user_loader
def user_loader(email):
    from lib.login.login_management import User, authorized_user
    from database import User as DbUser

    db_user = DbUser.query.filter_by(email=email).first()

    if db_user is not None and authorized_user(db_user):
        user = User()
        user.id = db_user.email
        user.firstname = db_user.firstname
        user.lastname = db_user.lastname
        user.url_picture = db_user.url_picture
        user.is_admin = db_user.is_admin
        user.user_authorized = db_user.user_authorized

        return user

    return None


@login_manager.request_loader
def request_loader(request):
    from lib.login.login_management import User, authenticate
    email = request.form.get('email')
    password = request.form.get('email')

    if authenticate(email, password):
        user = User()
        user.id = email
        return User

    return None


@app.teardown_appcontext
def shutdown_session(exception=None):
    from database import db
    db.session.remove()


@app.template_filter()
def timesince(dt, default="just now"):
    """
    Returns string representing "time since" e.g.
    3 days ago, 5 hours ago etc.
    """

    now = datetime.utcnow()

    diff = now - dt

    periods = (
        (diff.days / 365, "year", "years"),
        (diff.days / 30, "month", "months"),
        (diff.days / 7, "week", "weeks"),
        (diff.days, "day", "days"),
        (diff.seconds / 3600, "hour", "hours"),
        (diff.seconds / 60, "minute", "minutes"),
        (diff.seconds, "second", "seconds"),
    )

    for period, singular, plural in periods:
        if period:
            return "%d %s ago" % (period, singular if period == 1 else plural)

    return default


if __name__ == '__main__':
    # Create DB
    print("Creating database")
    from database import db

    db.create_all()

    debug = True
    app.run(debug=debug, port=9000, host="0.0.0.0")
