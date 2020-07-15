from database.connector import open_session, close_session
from database.tables import User, Deployment
from flask import Blueprint
from flask_login import current_user
from lib.admin_decorators import admin_login_required
from lib.dgs121028p import get_poe_status
from lib.email_notification import send_confirmation_request
from lib.config_loader import add_domain_filter, del_domain_filter, get_cluster_desc, load_cluster_desc
from lib.config_loader import load_config, save_mail_config, set_email_signup
from lib.dgs121028p import turn_on_port, turn_off_port
import datetime, flask, flask_login, json, subprocess, time


webapp_admin_blueprint = Blueprint('app_admin', __name__, template_folder='templates')


@webapp_admin_blueprint.route("/config/cluster")
@flask_login.login_required
@admin_login_required
def dump_cluster_desc():
    return '<pre>' + json.dumps(get_cluster_desc(), indent=2) + '</pre>'
    

@webapp_admin_blueprint.route("/config/switches")
@flask_login.login_required
@admin_login_required
def switches():
    cluster_desc = get_cluster_desc()
    # Read the state of the nodes from the deployment table
    db_session = open_session()
    states = db_session.query(Deployment).filter_by(state = 'destroyed').all()
    node_states = {}
    for s in states:
        node_states[s.node_name] = s.state
    close_session(db_session)
    # Read the switch information
    all_switches = []
    for switch in cluster_desc['switches'].values():
        switch_desc = { 'name': switch['name'], 'ip': switch['ip'], 'ports': [] }
        for port in range(0, switch['port_nb']):
            # Get the PoE status (on or off)
            if port % 4 == 0:
                switch_desc['ports'].append({})
            switch_desc['ports'][-1][str(port + 1)] = {'port': port + 1, 'poe_state': 'UNKNOWN'}
        for node in cluster_desc['nodes'].values():
            if 'switch' in node and node['switch'] == switch['name']:
                port_row = int((node['port_number'] - 1) / 4)
                my_state = 'UNKNOWN'
                if node['name'] in node_states:
                    my_state = node_states[node['name']]
                switch_desc['ports'][port_row][str(node['port_number'])] = {
                        'port': node['port_number'], 'name': node['name'], 'ip': node['ip'],
                        'poe_state': 'ON', 'node_state': my_state }
        all_switches.append(switch_desc)
    return { 'switches': all_switches }
    

@webapp_admin_blueprint.route("/config/poe_status/<string:switch_name>")
@flask_login.login_required
@admin_login_required
def poe_status(switch_name):
    cluster_desc = get_cluster_desc()
    switch = cluster_desc['switches'][switch_name]
    poe = get_poe_status(switch['name'])
    status = []
    for port in range(0, switch['port_nb']):
        if poe[port] == '1':
            status.append('ON')
        elif poe[port] == '2':
            status.append('OFF')
        else:
            status.append('UNKNOWN')
    return { 'status': status }


@webapp_admin_blueprint.route("/config/turn_on/<string:switch_ports>")
@flask_login.login_required
@admin_login_required
def turn_on(switch_ports):
    cluster_desc = get_cluster_desc()
    switch_ports = switch_ports.split(',')
    switch = cluster_desc['switches'][switch_ports[0].split('-')[0]]
    if switch is not None:
        for port in switch_ports:
            turn_on_port(switch['ip'], port.split('-')[1])
        return {'status': 'ok' }
    else:
        return {'status': 'ko' }


@webapp_admin_blueprint.route("/config/turn_off/<switch_ports>")
@flask_login.login_required
@admin_login_required
def turn_off(switch_ports):
    cluster_desc = get_cluster_desc()
    switch_ports = switch_ports.split(',')
    switch = cluster_desc['switches'][switch_ports[0].split('-')[0]]
    if switch is not None:
        for port in switch_ports:
            turn_off_port(switch['ip'], port.split('-')[1])
        return {'status': 'ok' }
    else:
        return {'status': 'ko' }


@webapp_admin_blueprint.route("/config/analyze_port/<string:switch_ports>")
@flask_login.login_required
@admin_login_required
def analyze_port(switch_ports):
    cluster_desc = get_cluster_desc()
    switch_ports = switch_ports.split(',')
    switch = cluster_desc['switches'][switch_ports[0].split('-')[0]]
    if switch is None:
        return {'status': 'ko' }
    #TODO Check there is no deployment using the node attached to this port
    for port in switch_ports:
        port_number = port.split('-')[1]
        # Turn off the port
        turn_off_port(switch['ip'], port_number)
        time.sleep(1)
        # Turn on the port
        turn_on_port(switch['ip'], port_number)
        time.sleep(5)
        # Listening DHCP Requests during 10 seconds
        cmd = "sudo tshark -nni eth0 -w /tmp/port.pcap -a duration:10 port 67 and 68"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                universal_newlines=True)
        print(process.stdout.split('\n'))
        # Analyzing the captured requests
        cmd = "tshark -r /tmp/port.pcap -Y 'bootp.option.type == 53 and bootp.ip.client == 0.0.0.0' -T fields -e frame.time \
                -e bootp.ip.client -e bootp.hw.mac_addr | awk '{ print $7 }' | uniq"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                universal_newlines=True)
        mac = process.stdout.split('\n')
        print(mac)
        return { 'status': 'ko' }



@webapp_admin_blueprint.route("/config/add_switch", methods=["POST"])
@flask_login.login_required
@admin_login_required
def add_switch():
    name  = flask.request.form.get("name")
    ip  = flask.request.form.get("ip")
    community  = flask.request.form.get("community")
    port_nb = int(flask.request.form.get("port_nb"))
    master_port  = int(flask.request.form.get("master_port"))
    oid  = flask.request.form.get("oid")
    # Remove the last digit that identifies the first port of the switch
    switch_oid = oid[:oid.rindex('.')]
    # The offset to add to reach a specific port
    oid_offset = int(oid[oid.rindex('.') + 1:]) - 1
    with open('cluster_desc/switches/%s.json' % name, 'w+') as json_file:
        json.dump({ 'name': name, 'ip': ip, 'community': community, 'port_nb': port_nb, 'master_port': master_port,
            'oid': switch_oid, 'oid_offset': oid_offset }, json_file, indent=4)
    load_cluster_desc()
    return flask.redirect(flask.url_for("app.admin"))
    

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
