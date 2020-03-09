from flask import Blueprint
import flask
import datetime
import flask_login
from flask_login import current_user
from fsm import deployment_initial_state

webapp_blueprint = Blueprint('app', __name__,
                             template_folder='templates')


@webapp_blueprint.route("/server/take/<string:server_info>")
@flask_login.login_required
def take(server_info):
    from lib.config.cluster_config import CLUSTER_CONFIG
    from database import Deployment, User
    from database import db

    db_user = User.query.filter_by(email=current_user.id).first()
    # Delete previous deployments still in initialized state
    Deployment.query.filter_by(user_id=db_user.id, state="initialized").delete();
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
        db.session.add(new_deployment)
        db.session.commit()

    return flask.render_template("form_take.html.jinja2",
                                 server_ids=server_ids,
                                 server_names=server_names,
                                 environments=CLUSTER_CONFIG.get("environments"))


@webapp_blueprint.route("/server/process_take/", methods=["POST"])
@flask_login.login_required
def process_take():
    from database import Deployment, User
    from database import db

    db_user = User.query.filter_by(email=current_user.id).first()
    deployments = Deployment.query.filter_by(user_id=db_user.id, state="initialized").all()

    for d in deployments:
        d.name = flask.request.form.get("name")
        d.public_key = flask.request.form.get("public_key")
        d.init_script = flask.request.form.get("init_script")
        pwd = flask.request.form.get("c9pwd")
        if pwd.strip():
            d.c9pwd = pwd
        d.environment = flask.request.form.get("environment")
        d.duration = flask.request.form.get("duration")
        d.start_date = datetime.datetime.utcnow()
        d.state = deployment_initial_state
    db.session.commit()

    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/reboot/<string:server_id>")
@flask_login.login_required
def ask_reboot(server_id):
    from database import Deployment, User
    from database import db

    db_user = User.query.filter_by(email=current_user.id).first()
    # Verify the node belongs to my deployments
    my_deployment = Deployment.query.filter(Deployment.user_id == db_user.id, Deployment.server_id == server_id,
                                            Deployment.state != "destroyed").first();
    if my_deployment is not None:
        my_deployment.label = my_deployment.state
        my_deployment.init_reboot()
    db.session.commit()
    db.session.close()
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/redeploy/<string:server_id>")
@flask_login.login_required
def ask_redeploy(server_id):
    from database import Deployment, User
    from database import db

    db_user = User.query.filter_by(email=current_user.id).first()
    # Verify the node belongs to my deployments
    my_deployment = Deployment.query.filter(Deployment.user_id == db_user.id, Deployment.server_id == server_id,
                                            Deployment.state != "destroyed").first();
    my_deployment.state = deployment_initial_state
    db.session.commit()
    db.session.close()
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/deployment/destroy/<string:deployment_ids>")
@flask_login.login_required
def ask_destruction(deployment_ids):
    from database import Deployment, User
    from database import db

    db_user = User.query.filter_by(email=current_user.id).first()

    for d in deployment_ids.split(","):
        deployment = Deployment.query.filter_by(id=d, user_id=db_user.id).first()
        if deployment is not None:
            deployment.ask_destruction()

            db.session.add(deployment)
    db.session.commit()

    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/")
@flask_login.login_required
def home():
    return flask.render_template("homepage_vuejs.html.jinja2")
