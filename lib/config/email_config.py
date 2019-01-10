from lib.config.config_loader import load_config


def get_email_configuration():
    email_config = load_config().get("mail", {})
    return {
        "smtp_server_url": email_config.get("smtp_address", "smtp.gmail.com"),
        "smtp_server_port": email_config.get("smtp_port", 587),
        "email": email_config.get("account", "SeduceCloud@gmail.com"),
        "password": email_config.get("password", "SeduceCloud+44"),
    }