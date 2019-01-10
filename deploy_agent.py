from flask import Flask
import json
from flask_apscheduler import APScheduler
from lib.config.tasks_config import TasksConfig
from lib.deployment import schedule_deployment

app = Flask(__name__)
app.config.from_object(TasksConfig())

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


@app.route("/deploy/<string:env_name>")
def deploy(env_name):
    print("Deploying %s" % env_name)
    schedule_deployment(env_name)
    result = {
        "status": "ok"
    }
    return json.dumps(result)


@app.route("/deployments")
def list_deployments():
    from lib.deployment import get_deployments
    return json.dumps(get_deployments())


if __name__ == '__main__':
    app.run(port=8888)
