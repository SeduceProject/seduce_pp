from database.connector import create_tables
from database.states import progress, no_fct
from state_exec import collect_nodes
import logging, logging.config, os, time


def logging_config():
    logging.config.fileConfig('logging-pitasks.conf', disable_existing_loggers=1)
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)


if __name__ == "__main__":
    STOP_FILE = 'tasksstop'
    logging_config()
    logger = logging.getLogger("CELERY_TASKS")

    create_tables(logger)
    logger.info("Analyzing the node states")
    while not os.path.isfile(STOP_FILE):
        # Node deployment processing
        for states in progress['deployment']:
            for state in reversed(states):
                if state not in no_fct:
                    collect_nodes(state)
        # Waiting for the node configuration
        time.sleep(3)
    if os.path.isfile(STOP_FILE):
        os.remove(STOP_FILE)
    logger.info("The piTasks service is stopped.")
