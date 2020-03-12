from database.connector import open_session, close_session
from database.tables import User
from database.states import user_initial_state, progress_forward
from lib.email.notification import send_confirmation_request
import logging


def new_user():
    logger = logging.getLogger("EMAIL")
    try:
        db_session = open_session()
        db_users = db_session.query(User).filter(User.state == user_initial_state).all()
        for user in db_users:
            logger.info("### User %s enters in 'created' state" % user.email)
            result = send_confirmation_request(user)
            logger.info(result)
            if result.get("success", False):
                user.email_confirmation_token = result["token"]
                progress_forward(user)
        close_session(db_session)
    except:
        logger.exception("Failed to send the confirmation email:")
