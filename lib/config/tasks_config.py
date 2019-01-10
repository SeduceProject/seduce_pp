class TasksConfig(object):
    JOBS = [
        {
            'id': 'job1',
            'func': 'lib.deployment:do_deployment_scheduling',
            'args': (),
            'trigger': 'interval',
            'seconds': 30
        },
        {
            'id': 'job2',
            'func': 'lib.deployment:do_check_deployments_and_update_status',
            'args': (),
            'trigger': 'interval',
            'seconds': 30
        }
    ]