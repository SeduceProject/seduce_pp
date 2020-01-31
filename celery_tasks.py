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


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # DEFAULT
    sender.add_periodic_task(5.0, send_confirmation_email.s(), name='send_confirmation_email')
    # COMPUTE
    sender.add_periodic_task(5.0, prepare_nfs_boot.s(), name='prepare_nfs_boot')
    sender.add_periodic_task(5.0, init_reboot_nfs.s(), name='init_reboot_nfs')
    sender.add_periodic_task(5.0, conclude_reboot_nfs.s(), name='conclude_reboot_nfs')
    sender.add_periodic_task(5.0, prepare_deployment.s(), name='prepare_deployment')
    sender.add_periodic_task(5.0, deploy_env.s(), name='deploy_env')
    sender.add_periodic_task(5.0, deploy_env_finished.s(), name='deploy_env_finished')

    sender.add_periodic_task(5.0, configure_sdcard_resize_boot.s(), name='configure_sdcard_resize_boot')
    sender.add_periodic_task(5.0, init_reboot_nfs_after_resize.s(), name='init_reboot_nfs_after_resize')
    sender.add_periodic_task(5.0, conclude_reboot_nfs_after_resize.s(), name='conclude_reboot_nfs_after_resize')
    sender.add_periodic_task(5.0, collect_partition_uuid.s(), name='collect_partition_uuid')
    sender.add_periodic_task(5.0, deploy_public_key.s(), name='deploy_public_key')

    sender.add_periodic_task(5.0, prepare_sdcard_boot.s(), name='prepare_sdcard_boot')
    sender.add_periodic_task(5.0, init_reboot_sdcard.s(), name='init_reboot_sdcard')
    sender.add_periodic_task(5.0, conclude_reboot_sdcard.s(), name='conclude_reboot_sdcard')
    sender.add_periodic_task(5.0, finish_deployment.s(), name='finish_deployment')

    sender.add_periodic_task(5.0, process_destruction.s(), name='process_destruction')
    sender.add_periodic_task(5.0, conclude_destruction.s(), name='conclude_destruction')

    sender.add_periodic_task(5.0, check_stuck_deployments.s(), name='check_stuck_deployments')


if __name__ == "__main__":
    import time

    while True:
        # DEFAULT
        #send_confirmation_email()

        # Start with the destruction of deployments
        conclude_destruction()
        process_destruction()

        # Deploy new environments on nodes (the reverse order is crucial !)
        finish_deployment()
        conclude_reboot_sdcard()
        on_reboot_sdcard()
        off_reboot_sdcard()
        do_sdcard_boot()
        prepare_sdcard_boot()
        check_authorized_keys()
        deploy_public_key()
        mount_public_key()
        collect_partition_uuid()
        sdcard_mount()
        conclude_reboot_nfs_after_resize()
        on_nfs_boot()
        off_nfs_boot()
        turn_on_after_resize()
        turn_off_after_resize()
        filesystem_check()
        configure_sdcard_resize_boot()
        mount_filesystem()
        deploy_env_finished()
        deploy_env()
        prepare_deployment()
        conclude_reboot_nfs()
        start_reboot_nfs()
        init_reboot_nfs()
        prepare_nfs_boot()

        #boot_stuck_deployments()
        #detect_stuck_deployments()

        # Do not decrease the sleep time (the time is configured from the node reboot time)
        time.sleep(3)
