import celery, logging


@celery.task()
def send_confirmation_email():
    from database import db
    from database import User
    from lib.email.notification import send_confirmation_request

    logger = logging.getLogger("EMAIL")
    logger.info("Checking users in 'created' state")
    users = User.query.filter_by(state="created").all()
    logger.info(len(users))
    for user in users:

        result = send_confirmation_request(user)

        if result.get("success", False):
            user.email_confirmation_token = result["token"]
            user.email_sent()

            db.session.add(user)
            db.session.commit()
