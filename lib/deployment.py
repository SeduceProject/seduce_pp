import subprocess
import uuid
import time
import threading

DEPLOYMENTS = []
deployment_lock = threading.Lock()
deployment_processes = []


def schedule_deployment(env_name):
    global DEPLOYMENTS

    new_deployment = {
        "id": str(uuid.uuid4()),
        "status": "not_yet_scheduled",
        "env_name": env_name,
        "creation_date": time.time(),
        "schedule_date": None,
        "start_date": None,
        "end_date": None,
        "pid": None
    }
    DEPLOYMENTS += [new_deployment]
    return new_deployment


def is_there_pending_deployment():
    non_finished_deployments = [d for d in DEPLOYMENTS if d.get("status") not in ["finished", "aborted"]]
    return len(non_finished_deployments) > 0


def do_deployment_scheduling():
    global deployment_lock
    global deployment_processes

    # Find deployment not yet scheduled, and mark them as scheduled
    deployment_lock.acquire()
    not_yet_scheduled_deployments = [d for d in DEPLOYMENTS if d.get("status") in ["not_yet_scheduled"]]
    for deployment in not_yet_scheduled_deployments:
        deployment["status"] = "scheduled"
        deployment["schedule_date"] = time.time()

    for deployment in not_yet_scheduled_deployments:
        deployment["status"] = "deploying"
        deployment["start_date"] = time.time()

        cmd = "sleep 30"
        # cmd = "deploy"

        print("deployment starting")
        p = subprocess.Popen(cmd, shell=True)
        deployment_processes += [p]
        deployment["pid"] = p.pid

    deployment_lock.release()

    return True


def do_check_deployments_and_update_status():
    global deployment_lock

    # Find deployment not yet scheduled, and mark them as scheduled
    deployment_lock.acquire()
    pending_deployments = [d for d in DEPLOYMENTS if d.get("status") in ["deploying"]]

    for deployment in pending_deployments:

        corresponding_processes = [p for p in deployment_processes if p.pid == deployment.get("pid")]

        if len(corresponding_processes) == 0:
            deployment["status"] = "aborted"

        corresponding_process = corresponding_processes[0]
        corresponding_process.poll()

        if corresponding_process.returncode is None:
            continue

        if corresponding_process.returncode == 0:
            deployment["status"] = "finished"
            deployment["end_date"] = time.time()

        if corresponding_process.returncode != 0:
            deployment["status"] = "aborted"
            deployment["end_date"] = time.time()

    deployment_lock.release()

    return []


def get_deployment(deployment_uiid):
    matching_deployment = [d for d in DEPLOYMENTS if d.get("uuid") == deployment_uiid]
    return None


def get_deployments():
    return DEPLOYMENTS
