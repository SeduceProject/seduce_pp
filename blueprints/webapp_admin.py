from database.connector import open_session, close_session
from database.tables import User, Deployment
from flask import Blueprint
from flask_login import current_user
from lib.admin_decorators import admin_login_required
from lib.email_notification import send_confirmation_request
from lib.config_loader import add_domain_filter, del_domain_filter, get_cluster_desc
from lib.config_loader import load_config, save_mail_config, set_email_signup
import datetime, flask, flask_login, json


webapp_admin_blueprint = Blueprint('app_admin', __name__, template_folder='templates')


@webapp_admin_blueprint.route("/config/cluster")
@flask_login.login_required
@admin_login_required
def dump_cluster_desc():
    return '<pre>' + json.dumps(get_cluster_desc(), indent=2) + '</pre>'
    

@webapp_admin_blueprint.route("/config/users")
@flask_login.login_required
@admin_login_required
def users():
    cluster_desc = get_cluster_desc()
    config = load_config()
    session = open_session()
    db_user = session.query(User).filter(User.email == current_user.id).first()
    authorized = []
    admin = []
    pending = []
    if db_user.is_admin:
        for user in session.query(User).all():
            if user.is_admin:
                category = admin
            elif user.user_authorized:
                category = authorized
            else:
                category = pending
            category.append({
                'id': user.id, 'email': user.email, 'firstname': user.firstname, 'lastname': user.lastname,
                'email_confirmed': user.email_confirmed
            })
    return json.dumps({
        "status": "ok",
        "user_info": {
            'filters': cluster_desc['email_filters'], 'admin': admin, 'authorized': authorized,
            'pending': pending, 'smtp_config': config['mail'], 'email_signup': cluster_desc['email_signup']
        }
    })


@webapp_admin_blueprint.route("/config/email_config", methods=["POST"])
@flask_login.login_required
@admin_login_required
def email_config():
    # Modify the email_signup parameter
    cluster_desc = get_cluster_desc()
    new_value = flask.request.form.get("esup_value") == 'true'
    if new_value != cluster_desc['email_signup']:
        set_email_signup(new_value)
    # Modify the SMTP configuration
    config = load_config()
    new_config = config['mail']
    new_server = flask.request.form.get('smtp_server')
    new_port = flask.request.form.get('smtp_port')
    new_user = flask.request.form.get('smtp_user')
    new_password = flask.request.form.get('smtp_pwd')
    smtp_change = False
    if len(new_server) > 0 and config['mail']['smtp_address'] != new_server:
        smtp_change = True
        new_config['smtp_address'] = new_server
    if len(new_port) > 0 and config['mail']['smtp_port'] != new_port:
        smtp_change = True
        new_config['smtp_port'] = new_port
    if len(new_user) > 0 and config['mail']['account'] != new_user:
        smtp_change = True
        new_config['account'] = new_user
    if len(new_password) > 0 and config['mail']['password'] != new_password:
        smtp_change = True
        new_config['password'] = new_password
    if smtp_change:
        save_mail_config(new_config)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/confirm_email/<string:user_id>")
@flask_login.login_required
@admin_login_required
def confirm_email(user_id):
    db_session = open_session()
    user = db_session.query(User).filter_by(id = user_id).first()
    email = user.email
    firstname = user.firstname
    close_session(db_session)
    send_confirmation_request(email, firstname)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/add_domain", methods=["POST"])
@flask_login.login_required
@admin_login_required
def add_domain():
    add_domain_filter(flask.request.form.get("email_filter"))
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/del_domain/<string:email_domain>")
@flask_login.login_required
@admin_login_required
def del_domain(email_domain):
    del_domain_filter(email_domain)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/add_admin/<string:user_id>")
@flask_login.login_required
@admin_login_required
def add_admin(user_id):
    db_session = open_session()
    admin_user = db_session.query(User).filter_by(id = user_id).first()
    admin_user.is_admin = 1
    close_session(db_session)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/del_admin/<string:user_id>")
@flask_login.login_required
@admin_login_required
def del_admin(user_id):
    db_session = open_session()
    admin_user = db_session.query(User).filter_by(id = user_id).first()
    admin_user.is_admin = 0
    close_session(db_session)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/add_user_auth/<string:user_id>")
@flask_login.login_required
@admin_login_required
def add_user_auth(user_id):
    db_session = open_session()
    common_user = db_session.query(User).filter_by(id = user_id).first()
    common_user.user_authorized = 1
    close_session(db_session)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/del_user_auth/<string:user_id>")
@flask_login.login_required
@admin_login_required
def del_user_auth(user_id):
    db_session = open_session()
    common_user = db_session.query(User).filter_by(id = user_id).first()
    common_user.user_authorized = 0
    close_session(db_session)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/del_user/<string:user_id>")
@flask_login.login_required
@admin_login_required
def del_user(user_id):
    db_session = open_session()
    db_session.query(Deployment).filter_by(user_id = user_id).delete()
    db_session.query(User).filter_by(id = user_id).delete()
    close_session(db_session)
    return flask.redirect(flask.url_for("app.admin"))


@webapp_admin_blueprint.route("/config/nginx_stream")
@flask_login.login_required
@admin_login_required
def nginx_stream():
    cluster_desc = get_cluster_desc()
    nginx_stream_config = """
## <stream config for pi.seduce.fr>
stream {
    """
    for idx, node in enumerate(cluster_desc["nodes"].values(), start=1):
        ssh_port_number = 22000 + idx
        server_ip = node.get("ip")
        nginx_stream_config += f"""
    upstream ssh_pi{idx} {{
        server {server_ip}:22;
    }}    
    server {{
        listen {ssh_port_number};

        proxy_pass ssh_pi{idx};
        ssl_preread on;
    }}
        """

    nginx_stream_config += """
}
## </stream config for pi.seduce.fr>   
    """
    return '<pre>' + nginx_stream_config + '</pre>'


@webapp_admin_blueprint.route("/config/nginx_http")
@flask_login.login_required
@admin_login_required
def nginx_http():
    cluster_desc = get_cluster_desc()
    nginx_http_config = """
## <http config for pi.seduce.fr>
"""

    for idx, node in enumerate(cluster_desc["nodes"].values(), start=1):
        ssh_port_number = 22000 + idx
        server_ip = node.get("ip")

        nginx_http_config += f"""
server {{
    listen 80;
    listen 443 ssl;
    server_name pi{idx}.seduce.fr;

    location / {{
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        client_max_body_size 5m;
        
        proxy_pass http://{server_ip}:8181;
    }}
    
    error_page 502 https://seduce.fr/maintenance;
}}
        """

        nginx_http_config += f"""
server {{
listen 80;
listen 443 ssl;
server_name  ~^(?<target_port>.+)\.pi4\.seduce\.fr$;

location / {{
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    client_max_body_size 5m;

    proxy_pass http://192.168.1.54:$target_port;
}}

#error_page 502 https://seduce.fr/maintenance;
}}
                """

    nginx_http_config += """
## </http config for pi.seduce.fr>
    """
    return '<pre>' + nginx_http_config + '</pre>'
