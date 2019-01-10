import configparser
import os


CONFIG_FILES_PATH = ["/etc/seducepp.conf", "~/seducepp.conf", "conf/seducepp/seducepp.conf"]

CONFIG_SINGLETON = None


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
            with open(config_file_path) as config_file:
                CONFIG_SINGLETON = config_file_to_dict(config_file_path)
                return CONFIG_SINGLETON
    raise LookupError("No configuration file found, please create a configuration file in one of these locations: %s" % (CONFIG_FILES_PATH))
