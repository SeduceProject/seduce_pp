from database.base import Base, db_name, engine, Session
from sqlalchemy import inspect


def create_tables(logger):
    inspector = inspect(engine)
    for sch in inspector.get_schema_names():
        if sch == db_name:
            if len(inspector.get_table_names(schema=sch)) == 0:
                logger.info("The database is empty. Create tables...")
                Base.metadata.create_all(engine)
                logger.info("Create the admin user")
                admin = "INSERT INTO user(email, _password, firstname, lastname, email_confirmed, user_authorized,\
                        is_admin) VALUES('admin@piseduce.fr',\
                        '$2b$12$qX460DWxWW3rzu5Q.Ot2juQDxb4lTA28rC6Y01BWvSt5i9Ey763du', 'Admin', 'Admin', 1, 1, 1)"
                db_session = open_session()
                db_session.execute(admin)
                close_session(db_session)


def open_session():
    return Session()


def close_session(session):
    session.commit()
    session.close()
