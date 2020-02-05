from celery import Celery
from tasks.email import *
from tasks.compute import *


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
    import time

    while True:
        # DEFAULT
        #send_confirmation_email()

        # Start with the destruction of deployments
        collect_nodes(conclude_destruction, 'destroying')
        collect_nodes(process_destruction, 'destruction_requested')

        # Reboot nodes from user requests
        collect_nodes(reboot_check_fct, 'reboot_check')
        collect_nodes(on_requested_fct, 'on_requested')
        collect_nodes(off_requested_fct, 'off_requested')

        # Deploy new environments on nodes (the reverse order is crucial !)
        collect_nodes(finish_deployment, 'sdcard_rebooted')
        collect_nodes(conclude_reboot_sdcard, 'sdcard_rebooting')
        collect_nodes(on_reboot_sdcard, 'off_sdcard_boot')
        collect_nodes(off_reboot_sdcard, 'configured_sdcard_boot')
        collect_nodes(do_sdcard_boot, 'sdcard_boot_ready')
        collect_nodes(prepare_sdcard_boot, 'public_key_deployed')
        collect_nodes(check_authorized_keys, 'authorized_keys')
        collect_nodes(deploy_public_key, 'mounted_public_key')
        collect_nodes(mount_public_key, 'collected_partition_uuid')
        collect_nodes(collect_partition_uuid, 'sdcard_mounted')
        collect_nodes(sdcard_mount, 'nfs_rebooted_after_resize')
        collect_nodes(conclude_reboot_nfs_after_resize, 'nfs_rebooting_after_resize')
        collect_nodes(on_nfs_boot, 'off_sdcard_resize')
        collect_nodes(off_nfs_boot, 'sdcard_resizing')
        collect_nodes(turn_on_after_resize, 'off_after_resize')
        collect_nodes(turn_off_after_resize, 'configured_sdcard_resize_boot')
        collect_nodes(filesystem_check, 'filesystem_ready')
        collect_nodes(configure_sdcard_resize_boot, 'filesystem_mounted')
        collect_nodes(mount_filesystem, 'environment_deployed')
        collect_nodes(deploy_env_finished, 'environment_deploying')
        collect_nodes(deploy_env, 'ready_deploy')
        collect_nodes(prepare_deployment, 'nfs_rebooted')
        collect_nodes(conclude_reboot_nfs, 'nfs_rebooting')
        collect_nodes(start_reboot_nfs, 'turn_on_nfs_boot')
        collect_nodes(init_reboot_nfs, 'configured_nfs_boot')
        collect_nodes(prepare_nfs_boot, 'created')

        # Do not decrease the sleep time (the time is configured from the node reboot time)
        time.sleep(3)
