from database.connector import open_session, close_session
from database.tables import User, Deployment
from flask import Blueprint
from flask_login import current_user
from lib.config.config_loader import get_cluster_desc
import flask, flask_login, json, logging, uuid


webappapp_api_blueprint = Blueprint('app_api', __name__, template_folder='templates')


@webappapp_api_blueprint.route("/api/authorized")
def authorized():
    logger = logging.getLogger("WEBAPP_API")
    logger.info(current_user, flush=True)
    logger.info(flask.request, flush=True)
    logger.info(flask.request.headers, flush=True)
    if current_user.is_authenticated:
        return "You are logged in! Sweet!"
    else:
        return 'Sorry, but unfortunately you\'re not logged in.', 401


@webappapp_api_blueprint.route("/api/deployment/<string:deployment_id>")
@flask_login.login_required
def deployment(deployment_id):
    session = open_session()
    deployment = session.query(Deployment).query.filter_by(id=deployment_id).first()
    dep_info = { "id": deployment.id, "state": deployment.state, "info": deployment.temp_info }
    close_session(session)
    if not deployment:
        return json.dumps({
            "status": "ko",
        })
    return json.dumps({
        "status": "ok",
        "deployment": {
            "id": deployment.id,
            "state": deployment.state,
            "info": deployment.temp_info
        }
    })


@webappapp_api_blueprint.route("/api/deployments")
@flask_login.login_required
def user_deployments():
    cluster_desc = get_cluster_desc()
    user = current_user
    misc = {}
    session = open_session()
    db_user = session.query(User).filter_by(email=user.id).first()
    deployments = session.query(Deployment).filter(Deployment.state != "destroyed").filter_by(user_id = db_user.id).all()
    deployment_info = {}
    for d in deployments:
        deployed = True
        if d.name not in deployment_info.keys():
            deployment_info[d.name] = {"name": d.name, "env": d.environment, "state": d.state, "user_id": d.user_id,
                    "ids": [], "server_names": [], "server_infos": [] }
        deployment_info[d.name]["ids"].append(d.id)
        for s in cluster_desc["nodes"].values():
            if s["name"] == d.node_name:
                deployment_info[d.name]["server_infos"].append({ "name": s["name"], "id": s["id"],
                    "state": d.state, "ip": s["ip"], "model": s["model"], "public_ip": s["public_ip"],
                    "public_port": s["public_port"], "password": d.system_pwd })
                deployment_info[d.name]["server_names"].append(s["name"])
    close_session(session)
    if not deployments:
        return json.dumps({
            "status": "ko",
        })

    return json.dumps({
        "status": "ok",
        "deployments": list(deployment_info.values())
    })


@webappapp_api_blueprint.route("/api/user_info")
@flask_login.login_required
def user_info():
    session = open_session()
    me = session.query(User).filter(User.email == current_user.id).first()
    if me.ssh_key is None:
        me.ssh_key = ''
    me_info = { "firstname": me.firstname, "lastname": me.lastname, "email": me.email,
            "ssh": me.ssh_key, "state": me.state }
    close_session(session)
    return json.dumps({
        "status": "ok",
        "my_user": me_info
    })


@webappapp_api_blueprint.route("/api/servers/available_servers")
@flask_login.login_required
def available_servers():
    cluster_desc = get_cluster_desc()
    session = open_session()
    db_user = session.query(User).filter(User.email == current_user.id).first()
    not_destroyed_deployments = session.query(Deployment).filter(Deployment.state != "destroyed").all()
    server_info = {}
    for s in cluster_desc["nodes"].values():
        server_info[s["name"]] = {"id": s["id"], "name": s["name"], "ip": s["ip"], "state": "free"}
    id2email = {}
    for d in not_destroyed_deployments:
        if d.user_id == db_user.id:
            server_info[d.node_name]["state"] = d.state
            server_info[d.node_name]["dname"] = d.name
            server_info[d.node_name]["env"] = d.environment
            if d.state.endswith('_check'):
                server_info[d.node_name]["progress"] = d.temp_info
            else:
                server_info[d.node_name]["progress"] = 100
        else:
            server_info[d.node_name]["state"] = "in_use"
            server_info[d.node_name]["progress"] = 100
            if d.user_id not in id2email.keys():
                foreign = session.query(User).filter(User.id == d.user_id).first()
                id2email[foreign.id] = foreign.email
            server_info[d.node_name]["dname"] = d.name
            server_info[d.node_name]["email"] = id2email[d.user_id]
    close_session(session)
    if not deployment:
        return json.dumps({
            "status": "ko"
        })
    return json.dumps({
        "status": "ok",
        "server_info": list(server_info.values())
    })
