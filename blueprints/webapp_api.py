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
