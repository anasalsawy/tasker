from sqlmodel import create_engine, Session
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()


def _build_database_url():
    connection_string = os.getenv('DB_CONNECTION_STRING', '').strip()
    if connection_string:
        return connection_string

    return ('postgresql://' + os.getenv('DB_USERNAME') + ':' + os.getenv('DB_PASSWORD') +
            '@' + os.getenv('DB_HOST') + ':' + os.getenv('DB_PORT') + '/' + os.getenv('DB_DATABASE'))


DATABASE_URL = _build_database_url()
_engine_options = {'echo': True}
if DATABASE_URL.startswith('sqlite'):
    _engine_options['connect_args'] = {'check_same_thread': False}

engine = create_engine(DATABASE_URL, **_engine_options)

SessionLocal = sessionmaker(class_=Session, bind=engine, autocommit=False, autoflush=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
