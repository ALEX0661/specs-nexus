import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get DATABASE_URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://specs_nexus_user:cybercats@localhost/specs_nexus_db")

# Create engine with SSL settings for production
is_production = os.getenv("ENVIRONMENT") == "production"
if is_production:
    engine = create_engine(DATABASE_URL, pool_recycle=300)
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()