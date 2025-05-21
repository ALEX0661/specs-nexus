import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from urllib.parse import urlparse, parse_qs

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Retrieve DATABASE_URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL is None:
    logger.error("DATABASE_URL environment variable is not set")
    raise ValueError("DATABASE_URL environment variable is not set")

# Log the raw DATABASE_URL for debugging
logger.info(f"Raw DATABASE_URL: {DATABASE_URL}")

# Replace 'mysql://' with 'mysql+pymysql://' for SQLAlchemy compatibility
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

# Validate the DATABASE_URL
try:
    parsed_url = urlparse(DATABASE_URL)
    if not parsed_url.scheme:
        raise ValueError("DATABASE_URL missing scheme (e.g., mysql+pymysql)")
    if not parsed_url.hostname:
        raise ValueError("DATABASE_URL missing hostname")
    if not parsed_url.path or parsed_url.path == "/":
        raise ValueError("DATABASE_URL missing database name")
    if parsed_url.port is None:
        logger.warning("No port specified in DATABASE_URL; defaulting to 3306")
        # Reconstruct URL with default MySQL port
        DATABASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}:3306{parsed_url.path}"
        if parsed_url.query:
            DATABASE_URL += f"?{parsed_url.query}"
    elif not (0 < parsed_url.port < 65536):
        raise ValueError(f"Invalid port in DATABASE_URL: {parsed_url.port}")
except Exception as e:
    logger.error(f"Invalid DATABASE_URL format: {e}")
    raise ValueError(f"Invalid DATABASE_URL format: {e}")

# Log the final DATABASE_URL
logger.info(f"Processed DATABASE_URL: {DATABASE_URL}")

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
    logger.error(f"Error initializing database: {e}")
    raise
