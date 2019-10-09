import celery
from celery.utils.log import get_task_logger
import logging

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)

@celery.task()
def send_confirmation_email():
    from database import db
    from database import User
    from lib.email.notification import send_confirmation_request

    logger.debug("Checking users in 'created' state")
    users = User.query.filter_by(state="created").all()
    logger.debug(len(users))
    for user in users:

        result = send_confirmation_request(user)

        if result.get("success", False):
            user.email_confirmation_token = result["token"]
            user.email_sent()

            db.session.add(user)
            db.session.commit()
