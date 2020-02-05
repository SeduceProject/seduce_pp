
# The states
user_initial_state = 'created'
user_states = [user_initial_state, 'waiting_confirmation_email', 'confirmed', 'waiting_authorization', 'authorized',
                'unauthorized']

# And some transitions between states.
user_transitions = [
    {'trigger': 'email_sent', 'source': user_initial_state, 'dest': 'waiting_confirmation_email'},
    {'trigger': 'confirm_email', 'source': 'waiting_confirmation_email', 'dest': 'confirmed'},
    {'trigger': 'notify_admin', 'source': 'confirmed', 'dest': 'waiting_authorization'},
    {'trigger': 'approve', 'source': 'waiting_authorization', 'dest': 'authorized'},
    {'trigger': 'disapprove', 'source': 'waiting_authorization', 'dest': 'unauthorized'},
    {'trigger': 'deauthorize', 'source': 'authorized', 'dest': 'unauthorized'},
    {'trigger': 'reauthorize', 'source': 'unauthorized', 'dest': 'authorized'},
]

# The states
deployment_initial_state = 'nfs_boot_conf'
deployment_states = [deployment_initial_state,
                     'nfs_boot_off',
                     'nfs_boot_on',
                     'env_copy',
                     'env_check',
                     'fs_mount',
                     'fs_conf',
                     'fs_check',
                     'resize_off',
                     'resize_on',
                     'resize_inprogress',
                     'resize_done',
                     'resize_check',
                     'ssh_key_mount',
                     'ssh_key_copy',
                     'ssh_key_user',
                     'fs_boot_conf',
                     'fs_boot_off',
                     'fs_boot_on',
                     'fs_boot_check',
                     'last_check',
                     'deployed',

                     'off_requested',
                     'on_requested',
                     'reboot_check',

                     'destroy_request',
                     'destroying',
                     'destroyed']

# And some transitions between states.
deployment_transitions = [
    {'trigger': 'nfs_boot_conf_fct', 'source': deployment_initial_state, 'dest': 'nfs_boot_off'},
    {'trigger': 'nfs_boot_off_fct', 'source': 'nfs_boot_off', 'dest': 'nfs_boot_on'},
    {'trigger': 'nfs_boot_on_fct', 'source': 'nfs_boot_on', 'dest': 'env_copy'},
    {'trigger': 'env_copy_fct', 'source': 'env_copy', 'dest': 'env_check'},
    {'trigger': 'env_check_fct', 'source': 'env_check', 'dest': 'fs_mount'},
    {'trigger': 'fs_mount_fct', 'source': 'fs_mount', 'dest': 'fs_conf'},
    {'trigger': 'fs_conf_fct', 'source': 'fs_conf', 'dest': 'fs_check'},
    {'trigger': 'fs_check_fct', 'source': 'fs_check', 'dest': 'resize_off'},
    {'trigger': 'resize_off_fct', 'source': 'resize_off', 'dest': 'resize_on'},
    {'trigger': 'resize_on_fct', 'source': 'resize_on', 'dest': 'resize_inprogress'},
    {'trigger': 'resize_inprogress_fct', 'source': 'resize_inprogress', 'dest': 'resize_done'},
    {'trigger': 'resize_done_fct', 'source': 'resize_done', 'dest': 'resize_check'},
    {'trigger': 'resize_check_fct', 'source': 'resize_check', 'dest': 'ssh_key_mount'},
    {'trigger': 'ssh_key_mount_fct', 'source': 'ssh_key_mount', 'dest': 'ssh_key_copy'},
    {'trigger': 'ssh_key_copy_fct', 'source': 'ssh_key_copy', 'dest': 'ssh_key_user'},
    {'trigger': 'ssh_key_user_fct', 'source': 'ssh_key_user', 'dest': 'fs_boot_conf'},
    {'trigger': 'fs_boot_conf_fct', 'source': 'fs_boot_conf', 'dest': 'fs_boot_off'},
    {'trigger': 'fs_boot_off_fct', 'source': 'fs_boot_off', 'dest': 'fs_boot_on'},
    {'trigger': 'fs_boot_on_fct', 'source': 'fs_boot_on', 'dest': 'fs_boot_check'},
    {'trigger': 'fs_boot_check_fct', 'source': 'fs_boot_check', 'dest': 'last_check'},
    {'trigger': 'last_check_fct', 'source': 'last_check', 'dest': 'deployed'},

    {'trigger': 'retry_resize', 'source': 'resize_check', 'dest': 'fs_mount'},

    {'trigger': 'init_reboot', 'source': '*', 'dest': 'off_requested'},
    {'trigger': 'off_requested_fct', 'source': 'off_requested', 'dest': 'on_requested'},
    {'trigger': 'on_requested_fct', 'source': 'on_requested', 'dest': 'reboot_check'},
    {'trigger': 'reboot_check_fct', 'source': 'reboot_check', 'dest': 'deployed'},

    {'trigger': 'ask_destruction', 'source': '*', 'dest': 'destroy_request'},
    {'trigger': 'destroy_request_fct', 'source': 'destroy_request', 'dest': 'destroying'},
    {'trigger': 'destroying_fct', 'source': 'destroying', 'dest': 'destroyed'},
]
