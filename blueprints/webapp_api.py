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

    deployment_info = {}
    for d in deployments:
        if d.name not in deployment_info.keys():
            deployment_info[d.name] = {"name": d.name, "ids": [], "server_ids": [], "server_names": [], "state": d.state, "user_id": d.user_id}
        deployment_info[d.name]["ids"].append(d.id)
        deployment_info[d.name]["server_ids"].append(d.server_id)
        for s in CLUSTER_CONFIG["nodes"]:
            if s["id"] == d.server_id:
                deployment_info[d.name]["server_names"].append(s["name"])

    if not deployments:
        return json.dumps({
            "status": "ko",
        })

    return json.dumps({
        "status": "ok",
        "deployments": list(deployment_info.values())
    })


@webappapp_api_blueprint.route("/api/servers/available_servers")
@flask_login.login_required
def available_servers():
    from lib.config.cluster_config import CLUSTER_CONFIG
    from database import Deployment, User, db

    db_user = User.query.filter_by(email=current_user.id).first()
    session = db.create_scoped_session()
    not_destroyed_deployments = session.query(Deployment).filter(Deployment.state != "destroyed").all()
    session.close()

    server_info = {}
    for s in CLUSTER_CONFIG["nodes"]:
        server_info[s["id"]] = {"id": s["id"], "name": s["name"], "ip": s["ip"], "state": "free"}
    id2email = {}
    for d in not_destroyed_deployments:
        if d.user_id == db_user.id:
            server_info[d.server_id]["state"] = d.state
            server_info[d.server_id]["dname"] = d.name
        else:
            server_info[d.server_id]["state"] = "in_use"
            if d.user_id not in id2email.keys():
                foreign = User.query.filter_by(id=d.user_id).first()
                id2email[foreign.id] = foreign.email
            server_info[d.server_id]["dname"] = id2email[foreign.id]

    if not deployment:
        return json.dumps({
            "status": "ko"
        })

    return json.dumps({
        "status": "ok",
        "server_info": list(server_info.values())
    })
