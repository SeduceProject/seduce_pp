
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
deployment_initial_state = 'created'
deployment_states = [deployment_initial_state,
                     'configured_nfs_boot',
                     'turn_on_nfs_boot',
                     'nfs_rebooting',
                     'nfs_rebooted',
                     'ready_deploy',
                     'environment_deploying',
                     'environment_deployed',
                     'filesystem_mounted',
                     'filesystem_ready',
                     'configured_sdcard_resize_boot',
                     'off_after_resize',
                     'sdcard_resizing',
                     'off_sdcard_resize',
                     'nfs_rebooting_after_resize',
                     'nfs_rebooted_after_resize',
                     'sdcard_mounted',
                     'collected_partition_uuid',
                     'mounted_public_key',
                     'public_key_deployed',
                     'sdcard_boot_ready',
                     'configured_sdcard_boot',
                     'off_sdcard_boot',
                     'sdcard_rebooting',
                     'sdcard_rebooted',
                     'deployed',

                     'destruction_requested',
                     'destroying',
                     'destroyed']

# And some transitions between states.
deployment_transitions = [
    {'trigger': 'prepare_nfs_boot', 'source': deployment_initial_state, 'dest': 'configured_nfs_boot'},
    {'trigger': 'init_reboot_nfs', 'source': 'configured_nfs_boot', 'dest': 'turn_on_nfs_boot'},
    {'trigger': 'start_reboot_nfs', 'source': 'turn_on_nfs_boot', 'dest': 'nfs_rebooting'},
    {'trigger': 'conclude_reboot_nfs', 'source': 'nfs_rebooting', 'dest': 'nfs_rebooted'},
    {'trigger': 'prepared_deployment', 'source': 'nfs_rebooted', 'dest': 'ready_deploy'},
    {'trigger': 'deploy_env', 'source': 'ready_deploy', 'dest': 'environment_deploying'},
    {'trigger': 'deploy_env_finished', 'source': 'environment_deploying', 'dest': 'environment_deployed'},
    {'trigger': 'mount_filesystem', 'source': 'environment_deployed', 'dest': 'filesystem_mounted'},
    {'trigger': 'configure_sdcard_resize_boot', 'source': 'filesystem_mounted', 'dest': 'filesystem_ready'},
    {'trigger': 'filesystem_check', 'source': 'filesystem_ready', 'dest': 'configured_sdcard_resize_boot'},
    {'trigger': 'turn_off_after_resize', 'source': 'configured_sdcard_resize_boot', 'dest': 'off_after_resize'},
    {'trigger': 'turn_on_after_resize', 'source': 'off_after_resize', 'dest': 'sdcard_resizing'},
    {'trigger': 'off_nfs_boot', 'source': 'sdcard_resizing', 'dest': 'off_sdcard_resize'},
    {'trigger': 'on_nfs_boot', 'source': 'off_sdcard_resize', 'dest': 'nfs_rebooting_after_resize'},
    {'trigger': 'conclude_reboot_nfs_after_resize', 'source': 'nfs_rebooting_after_resize', 'dest': 'nfs_rebooted_after_resize'},
    {'trigger': 'sdcard_mount', 'source': 'nfs_rebooted_after_resize', 'dest': 'sdcard_mounted'},
    {'trigger': 'collect_partition_uuid', 'source': 'sdcard_mounted', 'dest': 'collected_partition_uuid'},
    {'trigger': 'mount_public_key', 'source': 'collected_partition_uuid', 'dest': 'mounted_public_key'},
    {'trigger': 'deploy_public_key', 'source': 'mounted_public_key', 'dest': 'public_key_deployed'},
    {'trigger': 'prepare_sdcard_boot', 'source': 'public_key_deployed', 'dest': 'sdcard_boot_ready'},
    {'trigger': 'do_sdcard_boot', 'source': 'sdcard_boot_ready', 'dest': 'configured_sdcard_boot'},
    {'trigger': 'off_reboot_sdcard', 'source': 'configured_sdcard_boot', 'dest': 'off_sdcard_boot'},
    {'trigger': 'on_reboot_sdcard', 'source': 'off_sdcard_boot', 'dest': 'sdcard_rebooting'},
    {'trigger': 'conclude_reboot_sdcard', 'source': 'sdcard_rebooting', 'dest': 'sdcard_rebooted'},
    {'trigger': 'finish_deployment', 'source': 'sdcard_rebooted', 'dest': 'deployed'},

    #{'trigger': 'retry_configure_sdcard', 'source': 'filesystem_ready', 'dest': 'filesystem_mounted'},
    {'trigger': 'retry_resize', 'source': 'nfs_rebooted_after_resize', 'dest': 'environment_deployed'},


    {'trigger': 'ask_destruction', 'source': '*', 'dest': 'destruction_requested'},
    {'trigger': 'process_destruction', 'source': 'destruction_requested', 'dest': 'destroying'},
    {'trigger': 'conclude_destruction', 'source': 'destroying', 'dest': 'destroyed'},
]
