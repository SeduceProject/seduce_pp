from flask import Blueprint
import flask
import datetime
import flask_login
from flask_login import current_user

webapp_blueprint = Blueprint('app', __name__,
                             template_folder='templates')


@webapp_blueprint.route("/server/take/<string:server_id>")
@flask_login.login_required
def take(server_id):
    from lib.config.cluster_config import CLUSTER_CONFIG

    return flask.render_template("form_take.html.jinja2",
                                 server_id=server_id,
                                 environments=CLUSTER_CONFIG.get("environments"))


@webapp_blueprint.route("/server/process_take/<string:server_id>", methods=["POST"])
@flask_login.login_required
def process_take(server_id):
    from database import Deployment, User
    from database import db

    user = current_user
    user_email = user.id
    db_user = User.query.filter_by(email=user_email).first()

    new_deployment = Deployment()
    if "name" in flask.request.form:
        new_deployment.name = flask.request.form.get("name")
    new_deployment.public_key = flask.request.form.get("public_key")
    new_deployment.environment = flask.request.form.get("environment")
    new_deployment.duration = flask.request.form.get("duration")
    new_deployment.server_id = server_id
    new_deployment.start_date = datetime.datetime.utcnow()
    new_deployment.user_id = db_user.id

    db.session.add(new_deployment)
    db.session.commit()

    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/deployment/destroy/<string:deployment_id>")
@flask_login.login_required
def ask_destruction(deployment_id):
    from database import Deployment, User
    from database import db

    user = current_user
    user_email = user.id
    db_user = User.query.filter_by(email=user_email).first()

    deployment = Deployment.query.filter_by(id=deployment_id).first()

    if deployment is not None:

        deployment.ask_destruction()

        db.session.add(deployment)
        db.session.commit()

    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/")
@flask_login.login_required
def home():
    from lib.config.cluster_config import CLUSTER_CONFIG
    from database import Deployment, User

    user = current_user
    user_email = user.id
    db_user = User.query.filter_by(email=user_email).first()

    user_deployments = Deployment.query.filter_by(user_id=db_user.id).filter(Deployment.state != "destroyed").all()
    for deployment in user_deployments:
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        deployment.server = server
    deployment_ids = [d.server_id for d in Deployment.query.filter(Deployment.state != "destroyed").all()]
    available_servers = [s for s in CLUSTER_CONFIG["nodes"] if s.get("id") not in deployment_ids]
    return flask.render_template("homepage.html.jinja2", available_servers=available_servers, user_deployments=user_deployments)
