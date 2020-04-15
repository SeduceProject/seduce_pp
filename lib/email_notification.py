from database.connector import open_session, close_session
from database.tables import User
from lib.config_loader import load_config
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random, smtplib, string


TOKEN_LENGTH = 50


def get_email_configuration():
    email_config = load_config().get("mail", {})
    return {
        "smtp_server_url": email_config.get("smtp_address", "no_config"),
        "smtp_server_port": email_config.get("smtp_port", 587),
        "email": email_config.get("account","no_config"),
        "password": email_config.get("password", "no_config"),
    }


def send_confirmation_request(email, firstname):
    # Save the token to the database
    token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(TOKEN_LENGTH))
    db_session = open_session()
    user = db_session.query(User).filter_by(email = email).first()
    user.email_confirmation_token = token
    close_session(db_session)
    # Send the configuration email
    email_configuration = get_email_configuration()
    frontend_public_address = load_config().get("frontend", {}).get("public_address", "localhost:5000")
    fromaddr = email_configuration.get("email")
    toaddr = email
    msg = MIMEMultipart()
    msg['From'] = email_configuration.get("email")
    msg['To'] = toaddr
    msg['Subject'] = "Please confirm your email"
    body = """Hello %s,

Thanks for creating an account on the Seduce system.

In order to proceed with your account creation, please confirm your email by browsing on the following link:
https://%s/confirm_email/token/%s

Best Regards,
Seduce administrators
""" % (firstname, frontend_public_address, token)
    msg.attach(MIMEText(body, 'plain'))
    # Configure the smtp server
    smtp_server = smtplib.SMTP(email_configuration.get("smtp_server_url"), email_configuration.get("smtp_server_port"))
    smtp_server.ehlo()
    smtp_server.starttls()
    smtp_server.ehlo()
    smtp_server.login(fromaddr, email_configuration.get("password"))
    text = msg.as_string()
    smtp_server.sendmail(fromaddr, toaddr, text)
    smtp_server.quit()

    return {
        "success": True,
        "token": token
    }


def send_authorization_confirmation(email, firstname):
    email_configuration = get_email_configuration()
    frontend_public_address = load_config().get("frontend", {}).get("public_address", "localhost:5000")

    fromaddr = email_configuration.get("email")
    toaddr = user.email

    msg = MIMEMultipart()

    msg['From'] = email_configuration.get("email")
    msg['To'] = toaddr
    msg['Subject'] = "You account has been approved"

    body = """Hello %s,

You account has been approved by an admin, in consequence you can now log in:
https://%s/login

Best Regards,
Seduce system
""" % (firstname, frontend_public_address)

    msg.attach(MIMEText(body, 'plain'))

    smtp_server = smtplib.SMTP(email_configuration.get("smtp_server_url"), email_configuration.get("smtp_server_port"))
    smtp_server.ehlo()
    smtp_server.starttls()
    smtp_server.ehlo()
    smtp_server.login(fromaddr, email_configuration.get("password"))
    text = msg.as_string()
    smtp_server.sendmail(fromaddr, toaddr, text)
    smtp_server.quit()

    return {
        "success": True,
    }
