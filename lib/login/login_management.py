from database.connector import create_tables, open_session, close_session
from database.tables import User as dbUser


authorized_domains = [
    "@mines-nantes.fr",
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
    from initialization import bcrypt

    if email == "" or password == "" or email is None or password is None:
        return False
    db_session = open_session()
    user = db_session.query(dbUser).filter(dbUser.email == email).first()
    pwd_check = False
    auth_check = False
    if user is not None:
        pwd_check = bcrypt.check_password_hash(user.password, password)
        auth_check = authorized_user(user)
    close_session(db_session)
    return pwd_check and auth_check
