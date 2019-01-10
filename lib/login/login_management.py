import flask_login
from database import User as DbUser


class User(flask_login.UserMixin):
    pass


def authenticate(email, password):
    from database import bcrypt
    user = DbUser.query.filter_by(email=email).first()
    if user is not None:
        if user.user_authorized and bcrypt.check_password_hash(user.password, password):
            return True
    return False
