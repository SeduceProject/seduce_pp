import logging, logging.config, os, time
from celery import Celery
from tasks.compute import *
from tasks.email import *


def logging_config():
    logging.config.fileConfig('logging-tasks.conf', disable_existing_loggers=1)
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)


def make_celery(app):
    celery = Celery(app.import_name,
                    backend=app.config['CELERY_RESULT_BACKEND'],
                    broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

        def after_return(self, status, retval, task_id, args, kwargs, einfo):
            db.session.close()

    celery.Task = ContextTask
    return celery


# flask_app = Flask(__name__)
flask_app = db.app
flask_app.config.update(
    CELERY_BROKER_URL='redis://127.0.0.1:8879',
    CELERY_RESULT_BACKEND='redis://127.0.0.1:8879',
)
celery = make_celery(flask_app)


if __name__ == "__main__":
    STOP_FILE = 'tasksstop'
    logging_config()
    logger = logging.getLogger("CELERY_TASKS")
    logger.info("Analyzing the node states")


    while not os.path.isfile(STOP_FILE):
        # User management
        send_confirmation_email()

        ## WARNING: Deployment node states (the reverse order is crucial !)

        # Start with the destruction of deployments
        collect_nodes(destroying_fct, 'destroying')
        collect_nodes(destroy_request_fct, 'destroy_request')

        # Reboot nodes from user requests
        collect_nodes(reboot_check_fct, 'reboot_check')
        collect_nodes(on_requested_fct, 'on_requested')
        collect_nodes(off_requested_fct, 'off_requested')

        # Deploy new environments on nodes
        collect_nodes(last_check_fct, 'last_check')
        collect_nodes(user_conf_fct, 'user_conf')
        collect_nodes(system_conf_fct, 'system_conf')
        collect_nodes(wait_resizing_fct, 'wait_resizing')
        collect_nodes(resize_partition_fct, 'resize_partition')
        collect_nodes(mount_partition_fct, 'mount_partition')
        collect_nodes(create_partition_fct, 'create_partition')
        collect_nodes(delete_partition_fct, 'delete_partition')
        collect_nodes(env_check_fct, 'env_check')
        collect_nodes(env_copy_fct, 'env_copy')
        collect_nodes(nfs_boot_on_fct, 'nfs_boot_on')
        collect_nodes(nfs_boot_off_fct, 'nfs_boot_off')
        collect_nodes(nfs_boot_conf_fct, 'nfs_boot_conf')

        # Do not decrease the sleep time (the time is configured from the node reboot time)
        time.sleep(3)
    if os.path.isfile(STOP_FILE):
        os.remove(STOP_FILE)
    logger.info("The tasks service is stopped.")
