import logging
import logging.config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import engine
from app import models
from app.routes import auth, clearance, membership, events, announcements, officers, analytics, chat
from dotenv import load_dotenv
import os
import pathlib

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
env_path = pathlib.Path(__file__).parent / ".env"
if not env_path.exists():
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        logger.error(f".env file not found at either app/.env or .env")
        raise FileNotFoundError(f".env file not found")
    
logger.info(f"Loading .env file from {env_path}")
load_dotenv(env_path)

# Validate required environment variables
required_env_vars = ['CF_ACCESS_KEY_ID', 'CF_SECRET_ACCESS_KEY', 'CLOUDFLARE_R2_BUCKET', 'CLOUDFLARE_R2_ENDPOINT']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

# Print all environment variables for debugging
logger.info("Environment variables loaded:")
for var in required_env_vars:
    value = os.getenv(var)
    # Be careful not to log actual secret values in production
    if var in ['CF_ACCESS_KEY_ID', 'CF_SECRET_ACCESS_KEY']:
        logger.info(f"{var}: {'[SET]' if value else '[MISSING]'}")
    else:
        logger.info(f"{var}: {value if value else '[MISSING]'}")

if missing_vars:
    logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")

# Initialize FastAPI app
app = FastAPI(title="SPECS Nexus API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(clearance.router)
app.include_router(membership.router)
app.include_router(events.router)
app.include_router(announcements.router)
app.include_router(officers.router)
app.include_router(analytics.router)
app.include_router(chat.router)

models.Base.metadata.create_all(bind=engine)

@app.get("/")
def home():
    return {"message": "Welcome to SPECS Nexus API"}