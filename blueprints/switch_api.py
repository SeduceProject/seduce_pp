from flask import Blueprint
from lib.config.config_loader import get_cluster_desc
from lib.dgs121028p import acquire_gambit, get_ports_status, turn_on_port, turn_off_port
import flask, json, time

switch_api_blueprint = Blueprint('switch_api', __name__,
                                 template_folder='templates')


@switch_api_blueprint.route("/ports/turn_on/<int:port>")
def turn_on(port):
    cluster_desc = get_cluster_desc()
    turn_on_port(cluster_desc["switch"]["address"], port)
    return flask.redirect(flask.url_for("switch_api.ports"))


@switch_api_blueprint.route("/ports/turn_off/<int:port>")
def turn_off(port):
    cluster_desc = get_cluster_desc()
    turn_off_port(cluster_desc["switch"]["address"], port)
    return flask.redirect(flask.url_for("switch_api.ports"))


@switch_api_blueprint.route("/ports/data.json")
def get_updated_port_data():
    cluster_desc = get_cluster_desc()
    gambit_acquired = False
    gambit = None
    attempt_max = 10
    attempt_count = 0
    while not gambit_acquired and attempt_count < attempt_max:
        try:
            gambit = acquire_gambit(cluster_desc["switch"]["address"],
                                    cluster_desc["switch"]["username"],
                                    cluster_desc["switch"]["password"])
            gambit_acquired = True
        except:
            attempt_count += 1
            time.sleep(100)
    ports_status = get_ports_status(cluster_desc["switch"]["address"], gambit)
    return json.dumps(ports_status)


@switch_api_blueprint.route('/ports.html')
def ports():
    cluster_desc = get_cluster_desc()
    gambit_acquired = False
    gambit = None
    attempt_max = 10
    attempt_count = 0
    while not gambit_acquired and attempt_count < attempt_max:
        try:
            gambit = acquire_gambit(cluster_desc["switch"]["address"],
                                    cluster_desc["switch"]["username"],
                                    cluster_desc["switch"]["password"])
            gambit_acquired = True
        except:
            attempt_count += 1
            time.sleep(100)
    ports_status = get_ports_status(cluster_desc["switch"]["address"], gambit)
    return flask.render_template("switch_view.html.jinja2", ports_status=ports_status)
