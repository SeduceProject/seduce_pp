from database.connector import open_session, close_session
from database.states import progress_forward
from database.tables import User
from flask import Blueprint, render_template
from glob import glob
from lib.decorators.admin_login_required import admin_login_required
import flask, flask_login, logging, subprocess


login_blueprint = Blueprint('login', __name__, template_folder='templates')


@login_blueprint.route('/login', methods=['GET', 'POST'])
@login_blueprint.route('/login?msg=<msg>', methods=['GET', 'POST'])
def login(msg=None):
    if len(glob('cluster_desc/nodes/node-*.json')) == 0:
        cmd = "ifconfig | grep -B 1 broadcast"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = process.stdout.decode('utf-8').split('\n')
        master_interface = output[0].split(':')[0]
        master_ip = output[1].split()[1]
        cmd = "route -n | grep -A 1 Gateway | tail -n 1 | awk '{ print $2 }'"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        gateway = process.stdout.decode('utf-8').strip()
        return flask.render_template("form_configure.html.jinja2",
                ip = master_ip, iface = master_interface, gateway_ip = gateway)
    else:
        from initialization import User as InitUser
        if flask.request.method == 'GET':
            next_url = flask.request.args.get("next")
            return render_template("login/login.html", next_url=next_url, msg=msg)
        email = flask.request.form.get('email', "")
        password = flask.request.form.get('password', "")
        next_url = flask.request.form.get('next_url', "/")
        db_session = open_session()
        user_account = db_session.query(User).filter(User.email == email).first()
        redirect_url = ''
        if (user_account is not None and user_account.email_confirmed and
                bcrypt.check_password_hash(user_account.password, password)):
            user = InitUser()
            user.id = email
            is_authenticated = flask_login.login_user(user)
            redirect_url = next_url if (next_url is not None and next_url != "None") else flask.url_for("app.home")
        else:
            redirect_url = flask.url_for("login.login", msg="You are not authorized to log in")
        close_session(db_session)
        return flask.redirect(redirect_url)


@login_blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
    if flask.request.method == 'GET':
        next_url = flask.request.args.get("next")
        return render_template("login/signup.html", next_url=next_url)
    email = flask.request.form['email']
    firstname = flask.request.form['firstname']
    lastname = flask.request.form['lastname']
    password = flask.request.form['password']
    confirm_password = flask.request.form['confirm_password']
    db_session = open_session()
    existing_email = db_session.query(User).filter(User.email == email).all()
    if password != confirm_password:
        return 'The two passwords are not identical!<a href="/signup">Try again</a>'
    if len(existing_email) > 0:
        return "Your email address '%s' already exists. <a href='/'>Try to login</a>" % email
    user = User()
    user.email = email
    user.firstname = firstname
    user.lastname = lastname
    user._set_password = password
    db_session.add(user)
    close_session(db_session)
    redirect_url = flask.url_for("login.confirmation_account_creation")
    return flask.redirect(redirect_url)


@login_blueprint.route('/confirmation_account_creation')
def confirmation_account_creation():
    return render_template("login/confirmation_account_creation.html")


@login_blueprint.route('/confirmation_account_confirmation')
def confirmation_account_confirmation():
    return render_template("login/confirmation_account_confirmation.html")


@login_blueprint.route('/confirm_email/token/<token>')
def confirm_email(token):
    logger = logging.getLogger("LOGIN")
    logger.info("Receive the token '%s' to confirm email" % token)
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.email_confirmation_token == token).first()
    if user_candidate is not None:
        if user_candidate.state == "waiting_confirmation_email":
            user_candidate.email_confirmed = True
            progress_forward(user_candidate)
            close_session(db_session)
        return flask.redirect(flask.url_for("login.confirmation_account_confirmation"))
    return "Bad request: could not find the given token '%s'" % (token)


@login_blueprint.route('/approve_user/token/<token>')
@admin_login_required
def approve_user(token):
    from lib.email.notification import send_authorization_confirmation
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.admin_authorization_token == token).first()
    if user_candidate is not None:
        user_candidate.approve()
        user_candidate.user_authorized = True
        db_session.add(user_candidate)
        close_session(db_session)
        send_authorization_confirmation(user_candidate)
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not the find given token '%s'" % (token)


@login_blueprint.route('/disapprove_user/token/<token>')
@admin_login_required
def disapprove_user(token):
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.admin_authorization_token == token).first()
    if user_candidate is not None:
        user_candidate.disapprove()
        user_candidate.user_authorized = False
        db_session.add(user_candidate)
        close_session(db_session)
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not find givent token '%s'" % (token)


@login_blueprint.route('/promote_user/<user_id>')
@admin_login_required
def promote_user(user_id):
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.id == user_id).first()
    if user_candidate is not None:
        user_candidate.is_admin = True
        db_session.add(user_candidate)
        close_session(db_session)
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route('/demote_user/<user_id>')
@admin_login_required
def demote_user(user_id):
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.id == user_id).first()
    if user_candidate is not None:
        user_candidate.is_admin = False
        db_session.add(user_candidate)
        close_session(db_session)
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route('/authorize_user/<user_id>')
@admin_login_required
def authorize_user(user_id):
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.id == user_id).first()
    if user_candidate is not None:
        if user_candidate.state == "waiting_authorization":
            user_candidate.approve()
        elif user_candidate.state == "unauthorized":
            user_candidate.reauthorize()
        user_candidate.user_authorized = True
        db_session.add(user_candidate)
        close_session(db_session)
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route('/deauthorize_user/<user_id>')
@admin_login_required
def deauthorize_user(user_id):
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.id == user_id).first()
    if user_candidate is not None:
        user_candidate.deauthorize()
        user_candidate.user_authorized = False
        db_session.add(user_candidate)
        close_session(db_session)
        return flask.redirect(flask.url_for("app.settings"))
    return "Bad request: could not a user with given id '%s'" % (user_id)


@login_blueprint.route("/logout")
@flask_login.login_required
def logout():
    flask_login.logout_user()
    return flask.redirect(flask.url_for("app.home"))
