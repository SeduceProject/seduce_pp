import flask_login
from database import User as DbUser


class User(flask_login.UserMixin):
    pass


authorized_domains = [
    "@inria.fr",
    "@imt-atlantique.fr",
    # "@imt-atlantique.net", # Students are not allowed yet
]


def authorized_user(user):
    if user.user_authorized:
        return True
    for authorized_domain in authorized_domains:
        if authorized_domain in user.email and user.email_confirmed:
            return True
    return False


def authenticate(email, password):
    from database import bcrypt

    if email == "" or password == "" or email is None or password is None:
        return False
    
    user = DbUser.query.filter_by(email=email).first()
    if user is not None:
        if bcrypt.check_password_hash(user.password, password):
            return authorized_user(user)
    return False
