from flask import Blueprint
import flask_login
import json

webappapp_api_blueprint = Blueprint('app_api', __name__,
                                    template_folder='templates')


@webappapp_api_blueprint.route("/api/deployment/<string:deployment_id>")
@flask_login.login_required
def deployment(deployment_id):
    from database import Deployment

    deployment = Deployment.query.filter_by(id=deployment_id).first()

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
    from database import Deployment
    from lib.config.cluster_config import CLUSTER_CONFIG

    deployments = Deployment.query.filter(Deployment.state != "destroyed").all()
    for deployment in deployments:
        server_candidates = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id]
        if server_candidates:
            deployment.server = server_candidates[0]

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
            "server": deployment.server
        } for deployment in deployments]
    })


@webappapp_api_blueprint.route("/api/servers/available_servers")
@flask_login.login_required
def available_servers():
    from lib.config.cluster_config import CLUSTER_CONFIG
    from database import Deployment, User

    deployment_ids = [d.server_id for d in Deployment.query.filter(Deployment.state != "destroyed").all()]
    available_servers = [s for s in CLUSTER_CONFIG["nodes"] if s.get("id") not in deployment_ids]

    if not deployment:
        return json.dumps({
            "status": "ko",
        })

    return json.dumps({
        "status": "ok",
        "servers": available_servers
    })
