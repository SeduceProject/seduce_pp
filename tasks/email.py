import celery, logging


@celery.task()
def send_confirmation_email():
    from database import db
    from database import User
    from lib.email.notification import send_confirmation_request

    logger = logging.getLogger("EMAIL")
    try:
        users = User.query.filter_by(state="created").all()
        for user in users:
            logger.info("### User %s enters in 'created' state" % user.email)
            result = send_confirmation_request(user)
            logger.info(result)
            if result.get("success", False):
                user.email_confirmation_token = result["token"]
                user.email_sent()
                db.session.add(user)
                db.session.commit()
    except:
        logger.exception("Failed to send the confirmation email:")
