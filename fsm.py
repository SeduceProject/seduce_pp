
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
                     'delete_partition',
                     'create_partition',
                     'mount_partition',
                     'resize_partition',
                     'wait_resizing',
                     'system_conf',
                     'user_conf',
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
    {'trigger': 'env_check_fct', 'source': 'env_check', 'dest': 'delete_partition'},
    {'trigger': 'delete_partition_fct', 'source': 'delete_partition', 'dest': 'create_partition'},
    {'trigger': 'create_partition_fct', 'source': 'create_partition', 'dest': 'mount_partition'},
    {'trigger': 'mount_partition_fct', 'source': 'mount_partition', 'dest': 'resize_partition'},
    {'trigger': 'resize_partition_fct', 'source': 'resize_partition', 'dest': 'wait_resizing'},
    {'trigger': 'wait_resizing_fct', 'source': 'wait_resizing', 'dest': 'system_conf'},
    {'trigger': 'system_conf_fct', 'source': 'system_conf', 'dest': 'user_conf'},
    {'trigger': 'user_conf_fct', 'source': 'user_conf', 'dest': 'last_check'},
    {'trigger': 'last_check_fct', 'source': 'last_check', 'dest': 'deployed'},
    
    {'trigger': 'init_reboot', 'source': '*', 'dest': 'off_requested'},
    {'trigger': 'off_requested_fct', 'source': 'off_requested', 'dest': 'on_requested'},
    {'trigger': 'on_requested_fct', 'source': 'on_requested', 'dest': 'reboot_check'},
    {'trigger': 'reboot_check_fct', 'source': 'reboot_check', 'dest': 'deployed'},

    {'trigger': 'ask_destruction', 'source': '*', 'dest': 'destroy_request'},
    {'trigger': 'destroy_request_fct', 'source': 'destroy_request', 'dest': 'destroying'},
    {'trigger': 'destroying_fct', 'source': 'destroying', 'dest': 'destroyed'},
]
