import logging


user_initial_state = 'user_created'
deployment_initial_state = 'nfs_boot_conf'

progress = {
        'deployment': [
            [ 'nfs_boot_conf', 'nfs_boot_off', 'nfs_boot_on', 'env_copy', 'env_check', 'delete_partition',
                'create_partition', 'mount_partition', 'resize_partition', 'wait_resizing', 'system_conf', 'user_conf',
                'user_script', 'deployed' ],
            [ 'img_create_part', 'img_format_part', 'img_copy', 'img_copy_check', 'img_customize', 'img_compress',
                'img_compress_check', 'img_upload', 'upload_check', 'deployed' ],
            [ 'destroy_request', 'destroying', 'destroyed' ],
            [ 'off_requested', 'on_requested', 'rebooting' ]
        ]
    }

no_fct = [ 'destroyed', 'deployed' ]

failure = [
        [ 'user_conf', 'off_requested' ]
    ]


def init_deployment_state(deployment):
    deployment.state = deployment_initial_state


def reboot_state(deployment):
    deployment.state = 'off_requested'


def destroy_state(deployment):
    deployment.state = 'destroy_request'


def progress_state(state_key, state):
    for states in progress[state_key]:
        if state in states:
            idx = states.index(state) + 1
            if idx >= len(states):
                raise Exception("No progress state for the current state '%s': Index is too high" % state)
            else:
                return states[ idx ]
    raise Exception("No progress state for the current state '%s'" % state)


def progress_forward(db_obj):
    if db_obj.state == 'rebooting':
        db_obj.state = db_obj.temp_info
    else:
        db_obj.state = progress_state(type(db_obj).__name__.lower(), db_obj.state)


def failure_state(state):
    for states in failure:
        if state in states:
            idx = states.index(state) + 1
            if idx >= len(states):
                raise Exception("No failure state for the current state '%s': Index is too high" % state)
            else:
                return states[ idx ]
    raise Exception("No failure state for the current state '%s'" % state)


def failure_forward(db_obj):
    db_obj.state = failure_state(db_obj.state)


# Return True if SSH connections must use the 'ssh_user' property defined in the environment description
def use_env_ssh_user(dep_state):
    try:
        last_nfs_state = progress['deployment'][0].index('system_conf')
        dep_idx = progress['deployment'][0].index(dep_state)
        return dep_idx > last_nfs_state
    except:
        return True
