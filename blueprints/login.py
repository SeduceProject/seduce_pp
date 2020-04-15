from database.connector import open_session, close_session
from database.states import progress_forward
from database.tables import User
from flask import Blueprint, render_template
from glob import glob
from lib.admin_decorators import admin_login_required
from lib.config_loader import get_cluster_desc
from lib.email_notification import get_email_configuration, send_confirmation_request
import flask, flask_login, logging, subprocess


login_blueprint = Blueprint('login', __name__, template_folder='templates')


@login_blueprint.route('/login', methods=['GET', 'POST'])
@login_blueprint.route('/login?msg=<msg>', methods=['GET', 'POST'])
def login(msg=None):
    from initialization import User as InitUser, bcrypt
    if len(glob('cluster_desc/nodes/node-*.json')) == 0:
        cmd = "cat /etc/dhcpcd.conf | grep ^static"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = process.stdout.decode('utf-8')
        dhcp_on = len(output) == 0
        cmd = "ifconfig | grep -B 1 broadcast"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = process.stdout.decode('utf-8').split('\n')
        master_interface = output[0].split(':')[0]
        master_ip = output[1].split()[1]
        cmd = "route -n | grep -A 1 Gateway | tail -n 1 | awk '{ print $2 }'"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        gateway = process.stdout.decode('utf-8').strip()
        return flask.render_template("form_configure.html.jinja2",
                ip = master_ip, iface = master_interface, gateway_ip = gateway, dhcp = dhcp_on)
    else:
        if flask.request.method == 'GET':
            next_url = flask.request.args.get("next")
            return render_template("login/login.html", next_url=next_url, msg=msg)
        email = flask.request.form.get('email', "")
        password = flask.request.form.get('password', "")
        next_url = flask.request.form.get('next_url', "/")
        db_session = open_session()
        user_account = db_session.query(User).filter(User.email == email).first()
        redirect_url = ''
        # User login
        if (user_account is not None and user_account.user_authorized and
                bcrypt.check_password_hash(user_account.password, password)):
            user = InitUser()
            user.id = email
            flask_login.login_user(user)
            redirect_url = next_url if (next_url is not None and next_url != "None") else flask.url_for("app.home")
        else:
            redirect_url = flask.url_for("login.login", msg="You are not authorized to log in")
        close_session(db_session)
        return flask.redirect(redirect_url)


@login_blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
    cluster_desc = get_cluster_desc()
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
    email_filters = cluster_desc['email_filters']
    filter_ok = len(email_filters) == 0
    for f in email_filters:
        if f in email:
            filter_ok = True
    if not filter_ok:
        return 'Wrong email address.\
                Your domain name is not in the authorized domains.\
                Please contact the administrator or <a href="/signup">try with another email address</a>'
    user = User()
    user.email = email
    user.firstname = firstname
    user.lastname = lastname
    user._set_password = password
    db_session.add(user)
    close_session(db_session)
    email_conf = get_email_configuration()
    if len(email_conf['smtp_server_url']) > 0 and email_conf['smtp_server_url'] != 'no_config':
        # Send an email to confirm the user email address
        send_confirmation_request(email, firstname)
    if cluster_desc['email_signup']:
        redirect_url = flask.url_for("login.confirmation_created_account")
    else:
        redirect_url = flask.url_for("login.wait_admin_approval")
    return flask.redirect(redirect_url)


@login_blueprint.route('/confirmation_created_account')
def confirmation_created_account():
    return render_template("login/confirmation_created_account.html")


@login_blueprint.route('/wait_admin_approval')
def wait_admin_approval():
    return render_template("login/wait_admin_approval.html")


@login_blueprint.route('/confirmation_authorized_account')
def confirmation_authorized_account():
    return render_template("login/confirmation_authorized_account.html")


@login_blueprint.route('/confirmation_email')
def confirmation_email():
    return render_template("login/confirmation_email.html")


@login_blueprint.route('/confirm_email/token/<token>')
def confirm_email(token):
    logger = logging.getLogger("LOGIN")
    logger.info("Receive the token '%s' to confirm email" % token)
    db_session = open_session()
    user_candidate = db_session.query(User).filter(User.email_confirmation_token == token).first()
    url = "Bad request: could not find the given token '%s'" % (token)
    if user_candidate is not None:
        user_candidate.email_confirmed = True
        if get_cluster_desc()['email_signup']:
            user_candidate.user_authorized = True
            url = flask.redirect(flask.url_for("login.confirmation_authorized_account"))
        else:
            url = flask.redirect(flask.url_for("login.confirmation_email"))
    close_session(db_session)
    return url


@login_blueprint.route("/logout")
@flask_login.login_required
def logout():
    flask_login.logout_user()
    return flask.redirect(flask.url_for("app.home"))
