import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get DATABASE_URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://specs_nexus_user:cybercats@localhost/specs_nexus_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()