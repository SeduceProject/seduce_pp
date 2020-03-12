from database.base import Session
from database.connector import create_tables
from database.tables import User as dbUser
from initialization import login_manager, app, User
from lib.login.login_management import authenticate, authorized_user
import datetime, flask, flask_login, initialization, logging, logging.config, database.connector


def logging_config():
    logging.config.fileConfig('logging-frontend.conf', disable_existing_loggers=1)


@login_manager.user_loader
def user_loader(user_email):
    db_session = Session()
    db_user = db_session.query(dbUser).filter(dbUser.email == user_email).first()
    db_session.close()
    if db_user is not None and authorized_user(db_user):
        user = User()
        user.id = db_user.email
        user.firstname = db_user.firstname
        user.lastname = db_user.lastname
        user.ssh_key = db_user.ssh_key
        user.is_admin = db_user.is_admin
        user.user_authorized = db_user.user_authorized
        return user
    return None


@login_manager.request_loader
def request_loader(request):
    email = request.form.get('email')
    password = request.form.get('email')
    if authenticate(email, password):
        user = User()
        user.id = email
        return User
    return None


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
    logging_config()
    create_tables()
    app.run(debug=True, port=9000, host="0.0.0.0")
