from flask import Blueprint
from flask_login import current_user
from lib.config.config_loader import get_cluster_desc
from lib.decorators.admin_login_required import admin_login_required
import datetime, flask, flask_login, json

webapp_admin_blueprint = Blueprint('app_admin', __name__,
                             template_folder='templates')


@webapp_admin_blueprint.route("/config/cluster")
@flask_login.login_required
@admin_login_required
def dump_cluster_desc():
    with open('cluster_desc.json', 'w') as cluster_desc:
        json.dump(get_cluster_desc(), cluster_desc, indent=2)
    return flask.redirect(flask.url_for("app.home"))
    

@webapp_admin_blueprint.route("/config/generate")
@flask_login.login_required
@admin_login_required
def generate_config():
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

    return flask.render_template("generate_configuration.html.jinja2",
                                 config=cluster_desc,
                                 nginx_stream_config=nginx_stream_config,
                                 nginx_http_config=nginx_http_config)
