from database.connector import create_tables, open_session, close_session
from database.states import process, state_desc
from database.tables import Deployment
from datetime import datetime
from lib.config_loader import load_cluster_desc
from state_exec import exec_node_fct
import logging, logging.config, os, time


def logging_config():
    logging.config.fileConfig("logging-pitasks.conf", disable_existing_loggers=1)
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)


if __name__ == "__main__":
    # This file used by the SystemD service
    STOP_FILE = "tasksstop"
    # Logging configuration
    logging_config()
    logger = logging.getLogger("PITASKS")
    # Create the DB tables
    create_tables(logger)
    # Build the cluster description information
    load_cluster_desc()
    # My logger
    # Update the updated_at times to continue deploying the nodes
    db_session = open_session()
    old_nodes = db_session.query(Deployment).filter(
            Deployment.state !="destroyed").filter(
            Deployment.state !="deployed").filter(
            Deployment.state !="booted").all()
    for node in old_nodes:
        # Try to rescue lost nodes
        if node.state == "lost" and node.temp_info is not None:
            node.process = "deployment"
            node.state = node.temp_info.replace("_post","")
            node.temp_info = None
        if node.state != "lost":
            node.updated_at = datetime.now()
    close_session(db_session)
    logger.info("# Analyzing the node states")
    while not os.path.isfile(STOP_FILE):
        try:
            # Retrieve the running deployments
            db_session = open_session()
            pending_nodes = db_session.query(Deployment).filter(
                    Deployment.state !="destroyed").filter(
                    Deployment.state !="deployed").filter(
                    Deployment.state !="lost").filter(
                    Deployment.state !="booted").all()
            if len(pending_nodes) > 0:
                logger.info("## Nb. of pending nodes: %d" % len(pending_nodes))
            # Sort the nodes according the list of states
            sorted_nodes = { key: [] for key in [item for state in process.values() for item in state ]}
            for node in pending_nodes:
                sorted_nodes[node.state.replace("_exec", "").replace("_post","")].append(node)
            # Execute the functions of the states
            for state in sorted_nodes:
                for node in sorted_nodes[state]:
                    state_fct = node.state
                    if not state_fct.endswith("_exec") and not state_fct.endswith("_post"):
                        if state_desc[node.state]["exec"]:
                            state_fct = node.state + "_exec"
                        else:
                            state_fct = node.state + "_post"
                    logger.info("[%s] enter in '%s' state" % (node.node_name, state_fct))
                    # Execute the function associated to the node state
                    if exec_node_fct(state_fct, node):
                        # Update the state of the node
                        if state_fct.endswith("_exec") and state_desc[state]["post"]:
                            node.state = state_fct.replace("_exec", "_post")
                        else:
                            process_list = process[node.process]
                            # The exec_node_fct can change the state, compute the new value of the node state
                            node_state = node.state.replace("_exec", "").replace("_post","")
                            state_idx = process_list.index(node_state)
                            if state_idx + 1 < len(process_list):
                                node.state = process_list[state_idx + 1]
                        node.updated_at = datetime.now()
                        logger.info("[%s] change the state to '%s'" % (node.node_name, node.state))
                    else:
                        # The node is not ready, test the reboot timeout and the lost timeout
                        if node.updated_at is None:
                            node.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        updated = datetime.strptime(str(node.updated_at), "%Y-%m-%d %H:%M:%S")
                        elapsedTime = (datetime.now() - updated).total_seconds()
                        reboot_timeout = state_desc[state]["before_reboot"]
                        do_lost = True
                        if reboot_timeout > 0 and node.process != "reboot":
                            if elapsedTime > reboot_timeout:
                                logger.warning("[%s] hard reboot the node" % node.node_name)
                                # Remember the last state
                                node.temp_info = node.state
                                node.process = "reboot"
                                node.state = process["reboot"][0]
                            else:
                                do_lost = False
                                logger.info("[%s] not ready since %d seconds" %(node.node_name, elapsedTime))
                        lost_timeout = state_desc[state]["lost"]
                        if do_lost and lost_timeout > 0:
                            if elapsedTime > lost_timeout:
                                logger.warning("[%s] node is lost. Stop monitoring it!" % node.node_name)
                                if node.process != "reboot":
                                    node.temp_info = node.state
                                node.state = "lost"
                            else:
                                logger.info("[%s] not ready since %d seconds" %(node.node_name, elapsedTime))
            close_session(db_session)
        except Exception as e:
            logger.exception("Error while reading the database")
        # Waiting for the node configuration
        time.sleep(3)
    if os.path.isfile(STOP_FILE):
        os.remove(STOP_FILE)
    logger.info("The piTasks service is stopped.")
