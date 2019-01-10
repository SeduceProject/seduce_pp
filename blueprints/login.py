from flask import Blueprint, render_template
import flask
import flask_login
from lib.decorators.admin_login_required import admin_login_required

login_blueprint = Blueprint('login', __name__,
                            template_folder='templates')


@login_blueprint.route('/login', methods=['GET', 'POST'])
@login_blueprint.route('/login?msg=<msg>', methods=['GET', 'POST'])
def login(msg=None):
    if flask.request.method == 'GET':
        next_url = flask.request.args.get("next")
        return render_template("login/login.html", next_url=next_url, msg=msg)
    from lib.login.login_management import User, authenticate
    email = flask.request.form['email']
    password = flask.request.form['password']
    next_url = flask.request.form['next_url']
    if authenticate(email, password):
        user = User()
        user.id = email
        is_authenticated = flask_login.login_user(user)
        redirect_url = next_url if (next_url is not None and next_url != "None") else flask.url_for("app.home")
        return flask.redirect(redirect_url)

    return flask.redirect(flask.url_for("login.login", msg="You are not authorized to log in"))


@login_blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
    from database import User
    from database import db
    if flask.request.method == 'GET':
        next_url = flask.request.args.get("next")
        return render_template("login/signup.html", next_url=next_url)
    email = flask.request.form['email']
    firstname = flask.request.form['firstname']
    lastname = flask.request.form['lastname']
    password = flask.request.form['password']
    confirm_password = flask.request.form['confirm_password']
    if password == confirm_password:
        user = User()
        user.email = email
        user.firstname = firstname
        user.lastname = lastname
        # The password is ciphered and salted in the database.py file
        user._set_password = password

        db.session.add(user)
        db.session.commit()

        redirect_url = flask.url_for("login.confirmation_account_creation")
        return flask.redirect(redirect_url)

    return 'Bad login'


@login_blueprint.route('/confirmation_account_creation')
def confirmation_account_creation():
    return render_template("login/confirmation_account_creation.html")


@login_blueprint.route('/confirmation_account_confirmation')
def confirmation_account_confirmation():
    return render_template("login/confirmation_account_confirmation.html")


@login_blueprint.route('/confirm_email/token/<token>')
def confirm_email(token):
    from database import User
    from database import db
    db.session.expire_all()
    user_candidate = User.query.filter_by(email_confirmation_token=token).first()

    if user_candidate is not None:
        if user_candidate.state == "waiting_confirmation_email":
            user_candidate.confirm_email()
            user_candidate.email_confirmed = True
            db.session.add(user_candidate)
            db.session.commit()
        return flask.redirect(flask.url_for("login.confirmation_account_confirmation"))

    return "Bad request: could not find the given token '%s'" % (token)


@login_blueprint.route('/approve_user/token/<token>')
@admin_login_required
def approve_user(token):
    from database import User
    from lib.email.notification import send_authorization_confirmation
    from database import db
    db.session.expire_all()
    user_candidate = User.query.filter_by(admin_authorization_token=token).first()

    if user_candidate is not None:
        user_candidate.approve()
        user_candidate.user_authorized = True
        db.session.add(user_candidate)
        db.session.commit()
        send_authorization_confirmation(user_candidate)
        return flask.redirect(flask.url_for("app.settings"))

    return "Bad request: could not the find given token '%s'" % (token)


@login_blueprint.route('/disapprove_user/token/<token>')
@admin_login_required
def disapprove_user(token):
    from database import User
    from database import db
    user_candidate = User.query.filter_by(admin_authorization_token=token).first()

    if user_candidate is not None:
        user_candidate.disapprove()
        user_candidate.user_authorized = False
        db.session.add(user_candidate)
        db.session.commit()
        return flask.redirect(flask.url_for("app.settings"))

    return "Bad request: could not find givent token '%s'" % (token)


@login_blueprint.route('/promote_user/<user_id>')
@admin_login_required
def promote_user(user_id):
    from database import User
    from database import db
    db.session.expire_all()
    user_candidate = User.query.filter_by(id=user_id).first()

    if user_candidate is not None:
        user_candidate.is_admin = True
        db.session.add(user_candidate)
        db.session.commit()
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route('/demote_user/<user_id>')
@admin_login_required
def demote_user(user_id):
    from database import User
    from database import db
    db.session.expire_all()
    user_candidate = User.query.filter_by(id=user_id).first()

    if user_candidate is not None:
        user_candidate.is_admin = False
        db.session.add(user_candidate)
        db.session.commit()
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route('/authorize_user/<user_id>')
@admin_login_required
def authorize_user(user_id):
    from database import User
    from database import db
    db.session.expire_all()
    user_candidate = User.query.filter_by(id=user_id).first()

    if user_candidate is not None:
        if user_candidate.state == "waiting_authorization":
            user_candidate.approve()
        elif user_candidate.state == "unauthorized":
            user_candidate.reauthorize()
        user_candidate.user_authorized = True
        db.session.add(user_candidate)
        db.session.commit()
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route('/deauthorize_user/<user_id>')
@admin_login_required
def deauthorize_user(user_id):
    from database import User
    from database import db
    db.session.expire_all()
    user_candidate = User.query.filter_by(id=user_id).first()

    if user_candidate is not None:
        user_candidate.deauthorize()
        user_candidate.user_authorized = False
        db.session.add(user_candidate)
        db.session.commit()
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route("/logout")
@flask_login.login_required
def logout():
    flask_login.logout_user()
    return flask.redirect(flask.url_for("app.home"))
