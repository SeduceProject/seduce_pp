from database.connector import open_session, close_session
from database.tables import User, Deployment
from flask import Blueprint
from flask_login import current_user
from lib.config_loader import get_cluster_desc
import copy, datetime, flask, flask_login, json, logging, uuid


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


@webappapp_api_blueprint.route("/api/resources/<string:res_type>")
@flask_login.login_required
def resources(res_type):
    cluster_desc = copy.deepcopy(get_cluster_desc())
    session = open_session()
    # Get my user_id
    db_user = session.query(User).filter(User.email == current_user.id).first()
    # Get information about the used resources
    not_destroyed_deployments = session.query(Deployment).filter(Deployment.state != "destroyed").all()
    used_nodes = {}
    id2email = {}
    for d in not_destroyed_deployments:
        if d.user_id == db_user.id:
            # This is one of my deployments
            used_nodes[d.node_name] = { 'user': 'me', 'dep_name': d.name, 'state': d.state }
        else:
            # This is not my deployment, get information about the user
            if d.user_id not in id2email:
                foreign = session.query(User).filter(User.id == d.user_id).first()
                id2email[foreign.id] = foreign.email
            used_nodes[d.node_name] = { 'user': id2email[d.user_id], 'dep_name': d.name }
        if d.start_date is not None:
            s_date = datetime.datetime.strptime(str(d.start_date), '%Y-%m-%d %H:%M:%S')
            used_nodes[d.node_name]['starts_at'] = s_date.strftime("%d %b. at %H:%M")
    close_session(session)
    result = {}
    for node in cluster_desc['nodes'].values():
        if res_type in node:
            if not node[res_type] in result:
                result[node[res_type]] = { 'name': node[res_type], 'values': [] }
            if node['name'] in used_nodes:
                for key in used_nodes[node['name']]:
                    node[key] = used_nodes[node['name']][key]
            else:
                node['user'] = ''
            result[node[res_type]]['values'].append(node)
    return { 'resources': list(result.values()) } 


@webappapp_api_blueprint.route("/api/deployment/<string:deployment_id>")
@flask_login.login_required
def deployment(deployment_id):
    session = open_session()
    deployment = session.query(Deployment).query.filter_by(id=deployment_id).first()
    dep_info = { "id": deployment.id, "state": deployment.state, "info": deployment.temp_info }
    if deployment.start_date is not None:
        s_date = datetime.datetime.strptime(str(deployment.start_date), '%Y-%m-%d %H:%M:%S')
        dep_info['starts_at'] = s_date.strftime("%d %b. at %H:%M")
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
    cluster_desc = copy.deepcopy(get_cluster_desc())
    user = current_user
    misc = {}
    session = open_session()
    db_user = session.query(User).filter_by(email=user.id).first()
    deployments = session.query(Deployment).filter(Deployment.state != "destroyed").filter_by(
            user_id = db_user.id).order_by(Deployment.node_name).all();
    deployment_info = {}
    for d in deployments:
        deployed = True
        if d.name not in deployment_info.keys():
            # Deployment state is used to show/hide both the 'destroy' and the 'More info' buttons
            deployment_info[d.name] = {"name": d.name, "state": d.state, "user_id": d.user_id,
                    "ids": [], "server_names": [], "server_infos": [] }
        deployment_info[d.name]["ids"].append(d.id)
        node_desc = cluster_desc["nodes"][d.node_name]
        deployment_info[d.name]["server_names"].append(node_desc["name"])
        if d.environment is not None:
            if d.start_date is not None:
                s_date = datetime.datetime.strptime(str(d.start_date), '%Y-%m-%d %H:%M:%S')
                node_desc['starts_at'] = s_date.strftime("%d %b. at %H:%M")
            if d.state == 'lost':
                node_desc['last_state'] = d.temp_info
            env_desc = cluster_desc["environments"][d.environment]
            web_interface = False
            if 'web' in env_desc:
                web_interface = env_desc['web']
            node_desc['number'] = int(node_desc["name"].split('-')[1])
            node_desc['env'] = d.environment
            node_desc['state'] = d.state
            if d.state.endswith('_check'):
                node_desc["progress"] = d.temp_info
            else:
                node_desc["progress"] = 100
            node_desc['password'] = d.system_pwd
            node_desc['web'] = web_interface
            node_desc['desc'] = env_desc['desc']
            deployment_info[d.name]["server_infos"].append(node_desc);
    close_session(session)
    return { "deployments": list(deployment_info.values()) }


@webappapp_api_blueprint.route("/api/user_info")
@flask_login.login_required
def user_info():
    session = open_session()
    me = session.query(User).filter(User.email == current_user.id).first()
    if me.ssh_key is None:
        me.ssh_key = ''
    if me.is_admin:
        status = 'Administrator'
    elif me.user_authorized:
        status = 'Authorized'
    else:
        status = 'Unknown (Contact your administrator)'
    me_info = { "firstname": me.firstname, "lastname": me.lastname, "email": me.email,
            "ssh": me.ssh_key, "status": status }
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


@webappapp_api_blueprint.route("/api/configuration/log")
def conf_log():
    my_data = []
    with open('first_boot_log.txt', 'r') as logfile:
        lines = logfile.readlines()[-16:]
        for l in lines:
            my_data.append(l.strip())
    return json.dumps({ "status": "ok", "data": my_data})
