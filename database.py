import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import URL
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

env_path=Path(__file__).resolve().parent/ ".env"
load_dotenv(env_path)

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    database=os.environ["DB_NAME"],
)

engine=create_engine(database_url,pool_pre_ping=True)

class Base(DeclarativeBase):
    pass