import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Retrieve the DATABASE_URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")

# Check if DATABASE_URL is None
if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable is not set")

# Ensure the URL uses the correct MySQL driver for SQLAlchemy
# Railway provides 'mysql://', but we need to ensure the driver is specified (e.g., 'mysql+pymysql://')
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

try:
    # Create the SQLAlchemy engine
    engine = create_engine(DATABASE_URL, echo=False)  # Set echo=True for debugging SQL queries

    # Create a configured "Session" class
    Session = sessionmaker(bind=engine)

    # Create a base class for declarative models
    Base = declarative_base()

    print("Database engine created successfully")
except Exception as e:
    print(f"Error creating database engine: {e}")
    raise
