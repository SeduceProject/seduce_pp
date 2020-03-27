from glob import glob
import configparser, json, logging, os


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
                return CONFIG_SINGLETON
    raise LookupError("No configuration file found, please create a configuration file in one of these locations: %s" % (CONFIG_FILES_PATH))


def get_cluster_desc():
    if CLUSTER_DESC is None:
        return load_cluster_desc()
    else:
        return CLUSTER_DESC


# Load the cluster information
def load_cluster_desc():
    logger = logging.getLogger("CONFIG_LOADER")
    global CLUSTER_DESC
    CLUSTER_DESC = {}
    with open('cluster_desc/main.json', 'r') as json_file:
        CLUSTER_DESC = json.load(json_file)
    CLUSTER_DESC['nodes'] = {}
    CLUSTER_DESC['environments'] = {}
    for node_json in sorted(glob('cluster_desc/nodes/*.json')):
        with open(node_json, 'r') as json_file:
            node_desc = json.load(json_file)
        CLUSTER_DESC['nodes'][node_desc['name']] = node_desc
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
