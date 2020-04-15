from lib.config_loader import load_config
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

db_url = load_config().get("db").get("connection_url")
db_name = db_url.split('/')[-1]
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
Base = declarative_base()
