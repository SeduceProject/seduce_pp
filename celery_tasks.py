import logging, logging.config, time
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
    logging_config()
    logger = logging.getLogger("CELERY_TASKS")
    logger.info("Analyzing the node states")


    while True:
        # User management
        #send_confirmation_email()

        ## WARNING: Deployment node states (the reverse order is crucial !)

        # Start with the destruction of deployments
        collect_nodes(destroying_fct, 'destroying')
        collect_nodes(destroy_request_fct, 'destroy_request')

        # Reboot nodes from user requests
        collect_nodes(reboot_check_fct, 'reboot_check')
        collect_nodes(on_requested_fct, 'on_requested')
        collect_nodes(off_requested_fct, 'off_requested')

        # Deploy tinycore environements
        collect_nodes(tc_ssh_user_fct, 'tc_ssh_user')
        collect_nodes(tc_resize_fct, 'tc_resize')
        collect_nodes(tc_fdisk_fct, 'tc_fdisk')
        collect_nodes(tc_reboot_fct, 'tc_reboot')
        collect_nodes(tc_conf_fct, 'tc_conf')

        # Deploy new environments on nodes
        collect_nodes(last_check_fct, 'last_check')
        collect_nodes(ssh_config_2_fct, 'ssh_config_2')
        collect_nodes(fs_boot_check_fct, 'fs_boot_check')
        collect_nodes(fs_boot_on_fct, 'fs_boot_on')
        collect_nodes(fs_boot_off_fct, 'fs_boot_off')
        collect_nodes(fs_boot_conf_fct, 'fs_boot_conf')
        collect_nodes(ssh_key_user_fct, 'ssh_key_user')
        collect_nodes(ssh_key_copy_fct, 'ssh_key_copy')
        collect_nodes(ssh_key_mount_fct, 'ssh_key_mount')
        collect_nodes(resize_check_fct, 'resize_check')
        collect_nodes(resize_done_fct, 'resize_done')
        collect_nodes(resize_inprogress_fct, 'resize_inprogress')
        collect_nodes(resize_on_fct, 'resize_on')
        collect_nodes(resize_off_fct, 'resize_off')
        collect_nodes(fs_check_fct, 'fs_check')
        collect_nodes(fs_conf_fct, 'fs_conf')
        collect_nodes(fs_mount_fct, 'fs_mount')
        collect_nodes(env_check_fct, 'env_check')
        collect_nodes(env_copy_fct, 'env_copy')
        collect_nodes(nfs_boot_on_fct, 'nfs_boot_on')
        collect_nodes(nfs_boot_off_fct, 'nfs_boot_off')
        collect_nodes(nfs_boot_conf_fct, 'nfs_boot_conf')

        # Do not decrease the sleep time (the time is configured from the node reboot time)
        time.sleep(3)
