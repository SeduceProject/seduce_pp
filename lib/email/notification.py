from lib.config.email_config import get_email_configuration
import smtplib
import random
import string
from lib.config.config_loader import load_config

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

TOKEN_LENGTH = 50


def send_confirmation_request(user):
    email_configuration = get_email_configuration()
    frontend_public_address = load_config().get("frontend", {}).get("public_address", "localhost:5000")

    token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(TOKEN_LENGTH))

    fromaddr = email_configuration.get("email")
    toaddr = user.email

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
""" % (user.firstname, frontend_public_address, token)

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
        "token": token
    }


def send_authorization_request(user):
    email_configuration = get_email_configuration()
    frontend_public_address = load_config().get("frontend", {}).get("public_address", "localhost:5000")

    token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(TOKEN_LENGTH))

    fromaddr = email_configuration.get("email")
    toaddr = fromaddr

    msg = MIMEMultipart()

    msg['From'] = email_configuration.get("email")
    msg['To'] = toaddr
    msg['Subject'] = "A user requested a new account"

    body = """Hello,

A user has made a request for an account creation. As he has successfully confirmed his email,
you now have to review his request in order to decide the request is accepted.

Here are the details of the request:
email: %s
firstname: %s
lastname: %s

In the case you approve his account, he we will get access to the Seduce system.
Do you approve the request?

Yes, I approve the request:
https://%s/approve_user/token/%s

No, I disapprove the request:
https://%s/disapprove_user/token/%s


Thanks for taking the time to review this request.

Best Regards,
Seduce system
""" % (user.email, user.firstname, user.lastname, frontend_public_address, token, frontend_public_address, token)

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
        "token": token
    }


def send_authorization_confirmation(user):
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
""" % (user.firstname, frontend_public_address)

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
