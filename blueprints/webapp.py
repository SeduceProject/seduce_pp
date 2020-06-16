from database.connector import open_session, close_session
from database.tables import Deployment, User
from database.states import deployment_initial_state, destroy_state, init_deployment_state, reboot_state
from flask import Blueprint
from flask_login import current_user
from glob import glob
from lib.admin_decorators import admin_login_required
from lib.config_loader import get_cluster_desc, load_cluster_desc
import datetime, flask, flask_login, json, random, shutil, string, subprocess


webapp_blueprint = Blueprint('app', __name__, template_folder='templates')


def new_password(stringLength=8):
    """Generate a random string of letters and digits """
    lettersAndDigits = string.ascii_letters + string.digits
    return ''.join(random.choice(lettersAndDigits) for i in range(stringLength))


@webapp_blueprint.route("/server/take/<string:server_info>")
@flask_login.login_required
def take(server_info):
    cluster_desc = get_cluster_desc()
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Delete previous deployments still in initialized state
    old_dep = db_session.query(Deployment).filter_by(user_id=db_user.id, state="initialized").delete()
    # Reserve the nodes to avoid other users to take them
    info = server_info.split(";")
    server_ids = info[0].split(",")
    server_names = info[1].replace(' ','').split(",")
    for n_name in server_names:
        new_deployment = Deployment()
        new_deployment.state = "initialized"
        new_deployment.node_name = n_name
        new_deployment.user_id = db_user.id
        new_deployment.name = "initialized"
        db_session.add(new_deployment)
    close_session(db_session)
    # Reload the cluster decription to add new environments
    load_cluster_desc()
    return flask.render_template("form_take.html.jinja2",
                                 server_ids=server_ids,
                                 server_names=server_names,
                                 environments=cluster_desc["environments"].values())


@webapp_blueprint.route("/server/process_take/", methods=["POST"])
@flask_login.login_required
def process_take():
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    deployments = db_session.query(Deployment).filter_by(user_id = db_user.id, state = "initialized").all()
    for d in deployments:
        d.name = flask.request.form.get("name")
        d.public_key = flask.request.form.get("public_key")
        d.init_script = flask.request.form.get("init_script")
        pwd = flask.request.form.get("sys_pwd").strip()
        if pwd:
            d.system_pwd = pwd[:50]
        else:
            d.system_pwd = new_password()
        d.environment = flask.request.form.get("environment")
        d.duration = flask.request.form.get("duration_text")
        d.system_size = flask.request.form.get("more_space")
        d.start_date = datetime.datetime.utcnow()
        d.state = deployment_initial_state
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/cancel/")
@flask_login.login_required
def cancel():
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Delete previous deployments still in initialized state
    old_dep = db_session.query(Deployment).filter_by(user_id=db_user.id, state="initialized").delete()
    close_session(db_session)
    return flask.redirect(flask.url_for("app.configuration"))


@webapp_blueprint.route("/user/ssh_put/", methods=["POST"])
@flask_login.login_required
def ssh_put():
    my_ssh = flask.request.form.get("ssh_key")
    if my_ssh is not None and len(my_ssh) > 0:
        db_session = open_session()
        db_user = db_session.query(User).filter_by(email = current_user.id).first()
        db_user.ssh_key = my_ssh
        close_session(db_session)
    return flask.redirect(flask.url_for("app.user"))


@webapp_blueprint.route("/user/pwd_put/", methods=["POST"])
@flask_login.login_required
def pwd_put():
    pwd = flask.request.form.get("password")
    confirm_pwd = flask.request.form.get("confirm_password")
    if pwd == confirm_pwd:
        db_session = open_session()
        db_user = db_session.query(User).filter_by(email = current_user.id).first()
        db_user._set_password = pwd
        close_session(db_session)
        return flask.redirect(flask.url_for("app.user"))
    else:
        return 'The two passwords are not identical!<a href="/user">Try again</a>'


@webapp_blueprint.route("/server/reboot/<string:n_name>")
@flask_login.login_required
def ask_reboot(n_name):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Verify the node belongs to my deployments
    my_deployment = db_session.query(Deployment).filter_by(user_id = db_user.id,
            node_name = n_name).filter(Deployment.state != "destroyed").first()
    if my_deployment is not None:
        # Do not remember the 'lost' state but the state before it
        if my_deployment.state != 'lost':
            my_deployment.temp_info = my_deployment.state
        reboot_state(my_deployment)
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/redeploy/<string:n_name>")
@flask_login.login_required
def ask_redeploy(n_name):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    # Verify the node belongs to my deployments
    my_deployment = db_session.query(Deployment).filter_by(user_id = db_user.id,
            node_name = n_name).filter(Deployment.state != "destroyed").first()
    init_deployment_state(my_deployment)
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/deployment/destroy/<string:deployment_ids>")
@flask_login.login_required
def ask_destruction(deployment_ids):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    for d in deployment_ids.split(","):
        deployment = db_session.query(Deployment).filter_by(id = d, user_id = db_user.id).first()
        if deployment is not None:
            destroy_state(deployment)
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/server/save_env/<string:n_name>")
@flask_login.login_required
def save_env(n_name):
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    deployment = db_session.query(Deployment).filter_by(user_id = db_user.id, node_name = n_name).filter(
            Deployment.state != "destroyed").first()
    env_name = deployment.environment
    close_session(db_session)
    return flask.render_template("form_save_env.html.jinja2",
                                 environment=env_name,
                                 node_name=n_name)


@webapp_blueprint.route("/server/build_env/", methods=["POST"])
@flask_login.login_required
def build_env():
    cluster_desc = get_cluster_desc()
    db_session = open_session()
    db_user = db_session.query(User).filter_by(email = current_user.id).first()
    deployment = db_session.query(Deployment).filter_by(user_id = db_user.id,
            node_name=flask.request.form.get('node_name')).filter(Deployment.state != "destroyed").first()
    env = cluster_desc['environments'][deployment.environment]
    env['name'] = flask.request.form.get("user_env_name")
    env['img_name'] = env['name'] + '.img.gz'
    user_ssh_user = flask.request.form.get("user_ssh_user")
    if len(user_ssh_user) > 0:
        env['ssh_user'] = user_ssh_user
    env['type'] = 'user'
    env_file_path = cluster_desc['env_cfg_dir'] + env['name'].replace(' ', '_') + '.json'
    with open(env_file_path, 'w') as jsonfile:
        json.dump(env, jsonfile)
    deployment.state = 'img_create_part'
    deployment.temp_info = env['name']
    close_session(db_session)
    return flask.redirect(flask.url_for("app.home"))


@webapp_blueprint.route("/configuration/configure/", methods=["POST"])
def configure():
    if len(glob('cluster_desc/nodes/node-*.json')) > 0:
        return flask.redirect(flask.url_for("app.home"))
    old_ip = flask.request.form.get("my_ip")
    new_ip = flask.request.form.get("master_ip")
    # For DHCP configuratin, the master ip field is disable (users can not edit it)
    if new_ip is None:
        new_ip = old_ip
    dhcp_old = flask.request.form.get("dhcp_on")
    dhcp_conf = flask.request.form.get("dhcp_conf")
    switch_oid = flask.request.form.get("switch_oid")
    # Compare dhcp values to know if there is a change
    no_dhcp_change = (dhcp_conf is None and dhcp_old == 'False') or (dhcp_conf is not None and dhcp_old == 'True')
    if old_ip == new_ip and no_dhcp_change:
        # Generate the autoconf script
        shutil.copy('autoconf/files/master-conf-script', 'config.sh')
        cmd = "sed -i 's/GATEWAY_IP_CONF/%s/' config.sh" % flask.request.form.get("master_gateway")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/IFACE_CONF/%s/' config.sh" % flask.request.form.get("master_iface")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/MASTER_PORT_CONF/%s/' config.sh" % flask.request.form.get("master_port")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/SWITCH_IP_CONF/%s/' config.sh" % flask.request.form.get("switch_ip")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/NB_PORT_CONF/%s/' config.sh" % flask.request.form.get("nb_port")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/SNMP_COMMUNITY_NAME/%s/' config.sh" % flask.request.form.get("snmp_community")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        oid_offset = int(switch_oid[switch_oid.rindex('.') + 1:]) - 1
        cmd = "sed -i 's/SNMP_OID_CONF_OFFSET/%d/' config.sh" % oid_offset
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/SNMP_OID_CONF/%s/' config.sh" % switch_oid[:switch_oid.rindex('.')]
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/NETWORK_IP_CONF/%s/' config.sh" % new_ip[:new_ip.rindex('.')]
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/INC_IP_CONF/%s/' config.sh" % flask.request.form.get("inc_ip")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/CHANGE_ME_ROOT/%s/' config.sh" % flask.request.form.get("root_pwd")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "sed -i 's/CHANGE_ME_USER/%s/' config.sh" % flask.request.form.get("user_pwd")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        # Configure the pifrontend database access
        cmd = "sed -i 's/CHANGE_ME_USER/%s/' seducepp.conf" % flask.request.form.get("user_pwd")
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = "./config.sh &"
        config_log = open('first_boot_log.txt', 'w')
        process = subprocess.run(cmd, shell=True, stdout=config_log, stderr=config_log)
    else:
        # Change the IP configuration
        if dhcp_conf is None:
            shutil.copy('autoconf/files/dhcpcd.conf_static', '/etc/dhcpcd.conf')
            cmd = "sed -i 's/PIMASTERIP/%s/' /etc/dhcpcd.conf" % new_ip
            process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            cmd = "sed -i 's/GATEWAYIP/%s/' /etc/dhcpcd.conf" % flask.request.form.get("master_gateway")
            process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        else:
            shutil.copy('autoconf/files/dhcpcd.conf_dhcp', '/etc/dhcpcd.conf')
        cmd = "reboot"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return flask.redirect(flask.url_for("app.configuration"))


@webapp_blueprint.route("/configuration")
def configuration():
    return flask.render_template("first_boot_exec.html.jinja2")


@webapp_blueprint.route("/user")
@flask_login.login_required
def user():
    return flask.render_template("user_vuejs.html.jinja2")


@webapp_blueprint.route("/admin")
@admin_login_required
def admin():
    load_cluster_desc()
    return flask.render_template("admin.html.jinja2")


@webapp_blueprint.route("/")
@flask_login.login_required
def home():
    return flask.render_template("homepage_vuejs.html.jinja2")
