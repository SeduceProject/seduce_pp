import logging


user_initial_state = 'user_created'

process = {
        'deployment': [
            'boot_conf', 'turn_off', 'turn_on', 'ssh_nfs', 'env_copy', 'env_check', 
            'delete_partition', 'create_partition', 'mount_partition', 'resize_partition',
            'wait_resizing', 'system_conf', 'ssh_system', 'user_conf', 'user_script', 'deployed'
        ],
        'destroy': [
            'destroying', 'turn_off', 'destroyed'
        ],
        'reboot': [
            'turn_off', 'turn_on', 'coming_back'
        ],
        'boot_test': [
            'boot_conf', 'turn_off', 'turn_on', 'ssh_nfs', 'booted'
        ],
        'save_env': [
            'img_part', 'img_format', 'img_copy', 'img_copy_check', 'img_customize',
            'img_compress', 'img_compress_check', 'upload', 'upload_check', 'deployed'
        ]
}

# State names must not include '_exec' or '_post'
# lost timeout must be greater then reboot before_reboot
state_desc = {
    'boot_conf': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 30 },
    'turn_off': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 30 },
    'turn_on': { 'exec': True, 'post': True, 'before_reboot': 60, 'lost': 90 },
    'ssh_nfs': { 'exec': False, 'post': True, 'before_reboot': 45, 'lost': 60 },
    'env_copy': { 'exec': True, 'post': True, 'before_reboot': 0, 'lost': 30 },
    'env_check': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 400 },
    'delete_partition': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 45 },
    'create_partition': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 45 },
    'mount_partition': { 'exec': True, 'post': True, 'before_reboot': 0, 'lost': 30 },
    'resize_partition': { 'exec': True, 'post': True, 'before_reboot': 0, 'lost': 30 },
    'wait_resizing': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 90 },
    'system_conf': { 'exec': True, 'post': True, 'before_reboot': 0, 'lost': 30 },
    'ssh_system': { 'exec': False, 'post': True, 'before_reboot': 45, 'lost': 60 },
    'user_conf': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 30 },
    'user_script': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 30 },
    'deployed': { 'exec': False, 'post': False, 'before_reboot': 0, 'lost': 0 },

    'coming_back': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 60 },

    'destroying': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 30 },
    'destroyed': { 'exec': False, 'post': False, 'before_reboot': 0, 'lost': 0 },

    'booted': { 'exec': False, 'post': False, 'before_reboot': 0, 'lost': 0 },

    'img_part': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'img_format': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'img_copy': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'img_copy_check': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'img_customize': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'img_compress': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'img_compress_check': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'upload': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 },
    'upload_check': { 'exec': True, 'post': False, 'before_reboot': 0, 'lost': 0 }
}

# Return True if SSH connections must use the 'ssh_user' property defined in the environment description
def use_env_ssh_user(dep_state):
    try:
        last_nfs_state = process['deployment'].index('system_conf')
        dep_idx = process['deployment'].index(dep_state)
        return dep_idx > last_nfs_state
    except:
        return True
