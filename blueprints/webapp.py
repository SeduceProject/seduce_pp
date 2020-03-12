from database.connector import open_session, close_session
from database.tables import Deployment, User
from database.states import deployment_initial_state, destroy_state, init_deployment_state, reboot_state
from flask import Blueprint
from flask_login import current_user
from lib.config.cluster_config import CLUSTER_CONFIG
import datetime, flask, flask_login, random, string


webapp_blueprint = Blueprint('app', __name__, template_folder='templates')


def new_password(stringLength=8):
    """Generate a random string of letters and digits """
    lettersAndDigits = string.ascii_letters + string.digits
    return ''.join(random.choice(lettersAndDigits) for i in range(stringLength))


@webapp_blueprint.route("/server/take/<string:server_info>")
@flask_login.login_required
def take(server_info):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Delete previous deployments still in initialized state
    old_dep = db_session.query(Deployment).filter_by(user_id=db_user.id, state="initialized").delete()
    # Reserve the nodes to avoid other users to take them
    info = server_info.split(";")
    server_ids = info[0].split(",")
    server_names = info[1].split(",")
    for id in server_ids:
        new_deployment = Deployment()
        new_deployment.state = "initialized"
        new_deployment.server_id = id
        new_deployment.user_id = db_user.id
        new_deployment.name = "initialized"
        db_session.add(new_deployment)
    close_session(db_session)
    return flask.render_template("form_take.html.jinja2",
                                 server_ids=server_ids,
                                 server_names=server_names,
                                 environments=CLUSTER_CONFIG.get("environments"))


@webapp_blueprint.route("/server/cancel/")
@flask_login.login_required
def cancel():
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Delete previous deployments still in initialized state
    old_dep = db_session.query(Deployment).filter_by(user_id=db_user.id, state="initialized").delete()
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/process_take/", methods=["POST"])
@flask_login.login_required
def process_take():
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    deployments = db_session.query(Deployment).filter_by(user_id = db_user.id, state="initialized").all()
    for d in deployments:
        d.name = flask.request.form.get("name")
        d.public_key = flask.request.form.get("public_key")
        d.init_script = flask.request.form.get("init_script")
        pwd = flask.request.form.get("sys_pwd").strip()
        if pwd:
            d.system_pwd = pwd[:50]
        else:
            d.system_pwd = new_password()
        d.environment = flask.request.form.get("environment")
        d.duration = flask.request.form.get("duration")
        d.start_date = datetime.datetime.utcnow()
        d.state = deployment_initial_state
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/user/ssh_put/", methods=["POST"])
@flask_login.login_required
def ssh_put():
    my_ssh = flask.request.form.get("ssh_key")
    if my_ssh is not None and len(my_ssh) > 0:
        db_session = open_session()
        db_user = db_session.query(User).filter_by(email = current_user.id).first()
        db_user.ssh_key = my_ssh
        db.session.commit()
        db.session.close()
    return flask.redirect(flask.url_for("app.user"))


@webapp_blueprint.route("/user/pwd_put/", methods=["POST"])
@flask_login.login_required
def pwd_put():
    pwd = flask.request.form.get("password")
    confirm_pwd = flask.request.form.get("confirm_password")
    if pwd == confirm_pwd:
        db_session = open_session()
        db_user = db_session.query(User).filter_by(email = current_user.id).first()
        db_user._set_password = pwd
        close_session(db_session)
        return flask.redirect(flask.url_for("app.user"))
    else:
        return 'The two passwords are not identical!<a href="/user">Try again</a>'


@webapp_blueprint.route("/server/reboot/<string:server_id>")
@flask_login.login_required
def ask_reboot(server_id):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Verify the node belongs to my deployments
    my_deployment = db_session.query(Deployment).filter_by(user_id = db_user.id,
            server_id = server_id).filter(Deployment.state != "destroyed").first()
    if my_deployment is not None:
        my_deployment.label = my_deployment.state
        reboot_state(my_deployment)
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/redeploy/<string:server_id>")
@flask_login.login_required
def ask_redeploy(server_id):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Verify the node belongs to my deployments
    my_deployment = db_session.query(Deployment).filter_by(user_id = db_user.id,
            server_id = server_id).filter(Deployment.state != "destroyed").first()
    init_deployment_state(my_deployment)
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/deployment/destroy/<string:deployment_ids>")
@flask_login.login_required
def ask_destruction(deployment_ids):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    for d in deployment_ids.split(","):
        deployment = db_session.query(Deployment).filter_by(id = d, user_id = db_user.id).first()
        if deployment is not None:
            destroy_state(deployment)
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/user")
@flask_login.login_required
def user():
    return flask.render_template("user_vuejs.html.jinja2")


@webapp_blueprint.route("/")
@flask_login.login_required
def home():
    return flask.render_template("homepage_vuejs.html.jinja2")
