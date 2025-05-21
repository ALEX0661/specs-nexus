import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Retrieve DATABASE_URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable is not set")

# Replace 'mysql://' with 'mysql+pymysql://' for SQLAlchemy compatibility
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

try:
    # Create the SQLAlchemy engine with pool settings for Railway
    is_production = os.environ.get("ENVIRONMENT") == "production"
    if is_production:
        engine = create_engine(DATABASE_URL, pool_recycle=300, pool_pre_ping=True)
    else:
        engine = create_engine(DATABASE_URL)

    # Create a configured "SessionLocal" class
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create a base class for declarative models
    Base = declarative_base()

except Exception as e:
    print(f"Error initializing database: {e}")
    raise
