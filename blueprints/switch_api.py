import flask
from flask import Blueprint
from lib.dgs121028p import acquire_gambit, get_ports_status, turn_on_port, turn_off_port
import json
import time

switch_api_blueprint = Blueprint('switch_api', __name__,
                                 template_folder='templates')


@switch_api_blueprint.route("/ports/turn_on/<int:port>")
def turn_on(port):
    from lib.config.cluster_config import CLUSTER_CONFIG
    turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), port)
    return flask.redirect(flask.url_for("switch_api.ports"))


@switch_api_blueprint.route("/ports/turn_off/<int:port>")
def turn_off(port):
    from lib.config.cluster_config import CLUSTER_CONFIG
    turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), port)
    return flask.redirect(flask.url_for("switch_api.ports"))


@switch_api_blueprint.route("/ports/data.json")
def get_updated_port_data():
    from lib.config.cluster_config import CLUSTER_CONFIG
    gambit_acquired = False
    gambit = None
    attempt_max = 10
    attempt_count = 0
    while not gambit_acquired and attempt_count < attempt_max:
        try:
            gambit = acquire_gambit(CLUSTER_CONFIG.get("switch").get("address"),
                                    CLUSTER_CONFIG.get("switch").get("username"),
                                    CLUSTER_CONFIG.get("switch").get("password"))
            gambit_acquired = True
        except:
            attempt_count += 1
            time.sleep(100)
    ports_status = get_ports_status(CLUSTER_CONFIG.get("switch").get("address"), gambit)
    return json.dumps(ports_status)


@switch_api_blueprint.route('/ports.html')
def ports():
    from lib.config.cluster_config import CLUSTER_CONFIG
    gambit_acquired = False
    gambit = None
    attempt_max = 10
    attempt_count = 0
    while not gambit_acquired and attempt_count < attempt_max:
        try:
            gambit = acquire_gambit(CLUSTER_CONFIG.get("switch").get("address"),
                                    CLUSTER_CONFIG.get("switch").get("username"),
                                    CLUSTER_CONFIG.get("switch").get("password"))
            gambit_acquired = True
        except:
            attempt_count += 1
            time.sleep(100)
    ports_status = get_ports_status(CLUSTER_CONFIG.get("switch").get("address"), gambit)
    return flask.render_template("switch_view.html.jinja2", ports_status=ports_status)
