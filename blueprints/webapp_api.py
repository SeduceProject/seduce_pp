from flask import Blueprint
from flask_login import current_user
import flask_login
import json
import flask
import logging
import uuid

webappapp_api_blueprint = Blueprint('app_api', __name__,
                                    template_folder='templates')


@webappapp_api_blueprint.route("/api/authorized")
def authorized():
    print(current_user, flush=True)
    print(flask.request, flush=True)
    print(flask.request.headers, flush=True)
    if current_user.is_authenticated:
        return "You are logged in! Sweet!"
    else:
        return 'Sorry, but unfortunately you\'re not logged in.', 401


@webappapp_api_blueprint.route("/api/deployment/<string:deployment_id>")
@flask_login.login_required
def deployment(deployment_id):
    from database import Deployment, db

    session = db.create_scoped_session()
    deployment = session.query(Deployment).query.filter_by(id=deployment_id).first()
    session.close()

    if not deployment:
        return json.dumps({
            "status": "ko",
        })

    return json.dumps({
        "status": "ok",
        "deployment": {
            "id": deployment.id,
            "state": deployment.state,
            "label": deployment.label
        }
    })


@webappapp_api_blueprint.route("/api/deployments")
@flask_login.login_required
def user_deployments():
    from database import Deployment, User, db
    from lib.config.cluster_config import CLUSTER_CONFIG
    user = current_user

    misc = {}

    session = db.create_scoped_session()
    db_user = session.query(User).filter_by(email=user.id).first()
    deployments = session.query(Deployment).filter(Deployment.state != "destroyed").filter_by(user_id=db_user.id).all()
    session.close()

    for deployment in deployments:
        server_candidates = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id]
        if server_candidates:
            deployment.server = server_candidates[0]
        else:
            print("ici")

        environments_candidates = [environment for environment in CLUSTER_CONFIG.get("environments") if environment.get("name") == deployment.environment]
        if environments_candidates:
            environment = environments_candidates[0]
            for button_name, button_func in environment.get("buttons", {}).items():
                value = button_func(deployment.server)
                misc[deployment.id] = {
                    "button": {
                        "label": button_name,
                        "value": value
                    }
                }

    if not deployments:
        return json.dumps({
            "status": "ko",
        })

    return json.dumps({
        "status": "ok",
        "deployments":[{
            "id": deployment.id,
            "state": deployment.state,
            "label": deployment.label,
            "server": deployment.server,
            "misc": misc.get(deployment.id, {})
        } for deployment in deployments]
    })


@webappapp_api_blueprint.route("/api/servers/available_servers")
@flask_login.login_required
def available_servers():
    from lib.config.cluster_config import CLUSTER_CONFIG
    from database import Deployment, User, db

    session = db.create_scoped_session()
    not_destroyed_deployments = session.query(Deployment).filter(Deployment.state != "destroyed").all()
    session.close()

    deployment_ids = [d.server_id for d in not_destroyed_deployments]
    available_servers = [s for s in CLUSTER_CONFIG["nodes"] if s.get("id") not in deployment_ids]

    if not deployment:
        return json.dumps({
            "status": "ko",
        })

    return json.dumps({
        "status": "ok",
        "servers": available_servers
    })
