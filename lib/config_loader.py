from glob import glob
import configparser, json, logging, os, re


CONFIG_FILES_PATH = ["/etc/seducepp.conf", "seducepp.conf", "conf/seducepp/seducepp.conf"]

CONFIG_SINGLETON = None
CLUSTER_DESC = None


def config_file_to_dict(config_path):
    config = configparser.ConfigParser()
    successfully_read_files = config.read(config_path)

    if len(successfully_read_files) > 0:
        config_dict = {}
        for section in config.sections():
            config_dict[section] = {}
            for (key, value) in config.items(section):
                config_dict[section][key] = value
        return config_dict
    return None


def load_config():
    global CONFIG_SINGLETON
    if CONFIG_SINGLETON is not None:
        return CONFIG_SINGLETON
    for config_file_path in CONFIG_FILES_PATH:
        if os.path.exists(config_file_path):
            with open(config_file_path, 'r') as config_file:
                CONFIG_SINGLETON = config_file_to_dict(config_file_path)
            CONFIG_SINGLETON['path'] = config_file_path
            return CONFIG_SINGLETON
    raise LookupError("No configuration file found, please create a configuration file in one of these locations: %s"
            % (CONFIG_FILES_PATH))


def save_mail_config(mail_conf):
    global CONFIG_SINGLETON
    config_file = CONFIG_SINGLETON['path']
    del CONFIG_SINGLETON['path']
    CONFIG_SINGLETON['mail'] = mail_conf
    config = configparser.ConfigParser()
    config.read_dict(CONFIG_SINGLETON)
    with open(config_file, 'w') as conffile:
        config.write(conffile)
    CONFIG_SINGLETON = None
    load_config()


def get_cluster_desc():
    if CLUSTER_DESC is None:
        return load_cluster_desc()
    else:
        return CLUSTER_DESC


# Load the cluster information
def extract_number(node_name):
    return int(node_name.split('-')[1])


def load_cluster_desc():
    logger = logging.getLogger("CONFIG_LOADER")
    global CLUSTER_DESC
    CLUSTER_DESC = {}
    # Load the main properties
    with open('cluster_desc/main.json', 'r') as json_file:
        CLUSTER_DESC = json.load(json_file)
    CLUSTER_DESC['nodes'] = {}
    CLUSTER_DESC['environments'] = {}
    node_descriptions = []
    # Load the node descriptions
    for node_json in glob('cluster_desc/nodes/*.json'):
        with open(node_json, 'r') as json_file:
            node_desc = json.load(json_file)
        node_descriptions.append(node_desc)
    for desc in sorted(node_descriptions, key = lambda x: x['port_number']):
        CLUSTER_DESC['nodes'][desc['name']] = desc
    # Load the environment descriptions
    for env_json in sorted(glob('cluster_desc/environments/*.json')):
        try:
            with open(env_json, 'r') as json_file:
                env_desc = json.load(json_file)
            img_path = CLUSTER_DESC['img_dir'] + env_desc['img_name']
            if len(glob(img_path)) == 1:
                CLUSTER_DESC['environments'][env_desc['name']] = env_desc
            else:
                logger.error("Can not load the environment '%s', the file '%s' does not exist" %
                        (env_desc['name'], img_path))
        except:
            logger.exception("Can not load the environment '%s':")
    logger.info("%d nodes and %d environments loaded" %
            (len(CLUSTER_DESC['nodes']), len(CLUSTER_DESC['environments'])))
    return CLUSTER_DESC


def set_email_signup(new_value):
    global CLUSTER_DESC
    CLUSTER_DESC['email_signup'] = new_value
    return save_cluster_desc()


def add_domain_filter(new_filter):
    global CLUSTER_DESC
    CLUSTER_DESC['email_filters'].append(new_filter)
    return save_cluster_desc()


def del_domain_filter(new_filter):
    global CLUSTER_DESC
    CLUSTER_DESC['email_filters'].remove(new_filter)
    return save_cluster_desc()


def save_cluster_desc():
    logger = logging.getLogger("CONFIG_LOADER")
    del CLUSTER_DESC['nodes']
    del CLUSTER_DESC['environments']
    with open('cluster_desc/main.json', 'w') as jsonfile:
        json.dump(CLUSTER_DESC, jsonfile, indent=4)
    return load_cluster_desc()
