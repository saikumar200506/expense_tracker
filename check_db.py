from sqlalchemy import text

from database import engine

with engine.connect() as connection:
    result = connection.execute(text("SELECT current_database()"))
    database_name = result.scalar_one()
    print(f"Connected to database: {database_name}")