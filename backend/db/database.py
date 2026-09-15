from sqlmodel import create_engine, Session
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()


DATABASE_URL = ('postgresql://' + os.getenv('DB_USERNAME') + ':' + os.getenv('DB_PASSWORD') +
                '@' + os.getenv('DB_HOST') + ':' + os.getenv('DB_PORT') + '/' + os.getenv('DB_DATABASE')) \
    if not os.getenv('DB_CONNECTION_STRING') else os.getenv('DB_CONNECTION_STRING')

engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(class_=Session, bind=engine, autocommit=False, autoflush=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
