from database.base import Base, db_name, engine, Session
from sqlalchemy import inspect


def create_tables():
    inspector = inspect(engine)
    for sch in inspector.get_schema_names():
        if sch == db_name:
            if len(inspector.get_table_names(schema=sch)) == 0:
                print("The database is empty. Create tables...")
                Base.metadata.create_all(engine)


def append(values):
    session = Session()
    for v in values:
        print('Append %s' % v)
        session.add(v)
    session.commit()
    session.close()


def open_session():
    return Session()


def close_session(session):
    session.commit()
    session.close()
