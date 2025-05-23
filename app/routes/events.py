import logging
from datetime import datetime
import os
from typing import List, Optional
import boto3
from botocore.client import Config
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_user

logger = logging.getLogger("app.events")

router = APIRouter(prefix="/events", tags=["Events"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Configure boto3 client for Cloudflare R2
access_key_id = os.getenv('CF_ACCESS_KEY_ID')
secret_access_key = os.getenv('CF_SECRET_ACCESS_KEY')
bucket_name = os.getenv('CLOUDFLARE_R2_BUCKET')
endpoint_url = os.getenv('CLOUDFLARE_R2_ENDPOINT')

# Log environment variables for debugging (without showing secret values)
logger.debug(f"CF_ACCESS_KEY_ID set: {bool(access_key_id)}")
logger.debug(f"CF_SECRET_ACCESS_KEY set: {bool(secret_access_key)}")
logger.debug(f"CLOUDFLARE_R2_BUCKET: {bucket_name}")
logger.debug(f"CLOUDFLARE_R2_ENDPOINT: {endpoint_url}")

# Verify that bucket_name is not None before proceeding
if not bucket_name:
    logger.error("CLOUDFLARE_R2_BUCKET environment variable is not set")
    bucket_name = "specs-nexus-files"  # Fallback to hardcoded value

s3 = boto3.client(
    's3',
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

# Make the upload_to_r2 function async
async def upload_to_r2(file: UploadFile, object_key: str):
    try:
        # Get credentials from environment variables
        access_key = os.getenv("CF_ACCESS_KEY_ID")
        secret_key = os.getenv("CF_SECRET_ACCESS_KEY")
        bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET")
        endpoint_url = os.getenv("CLOUDFLARE_R2_ENDPOINT")
        
        # Use worker URL instead of direct R2 public URL
        worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "https://specsnexus-images.senya-videos.workers.dev")
        
        # Log credential availability for debugging
        logger.info(f"R2 Credentials - Access Key: {'Available' if access_key else 'Missing'}")
        logger.info(f"R2 Credentials - Secret Key: {'Available' if secret_key else 'Missing'}")
        logger.info(f"R2 Credentials - Bucket: {bucket_name or 'Missing'}")
        logger.info(f"R2 Credentials - Endpoint: {endpoint_url or 'Missing'}")
        logger.info(f"R2 Credentials - Worker URL: {worker_url or 'Missing'}")
        
        if not all([access_key, secret_key, bucket_name, endpoint_url, worker_url]):
            raise ValueError("Missing R2 credentials or configuration")
        
        # Create S3 client with explicit credentials
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )
        
        # Upload the file
        logger.info(f"Uploading file to R2: {object_key}")
        s3.upload_fileobj(file.file, bucket_name, object_key)
        
        # Use the worker URL for the uploaded file
        if worker_url.endswith('/'):
            file_url = f"{worker_url}{object_key}"
        else:
            file_url = f"{worker_url}/{object_key}"
            
        logger.info(f"File uploaded successfully: {file_url}")
        return file_url
        
    except Exception as e:
        logger.error(f"Error uploading file to R2: {str(e)}")
        raise

# Endpoint: GET /events/
# Description: Returns a list of all active (non-archived) events.
@router.get("/", response_model=List[schemas.EventSchema])
def get_events(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) fetching all active events")
    events = db.query(models.Event).filter(models.Event.archived == False).all()
    
    # Add is_participant flag to each event
    for event in events:
        event.is_participant = any(participant.id == current_user.id for participant in event.participants)
        
    logger.info(f"User {current_user.id} fetched {len(events)} events")
    return events

@router.post("/join/{event_id}", response_model=schemas.MessageResponse)
def join_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) attempting to join event {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for user {current_user.id}")
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Check if event registration is open
    now = datetime.utcnow()
    if event.registration_start and now < event.registration_start:
        logger.error(f"Registration for event {event_id} has not started yet for user {current_user.id}")
        raise HTTPException(status_code=403, detail="Registration for this event has not started yet")
    
    if event.registration_end and now > event.registration_end:
        logger.error(f"Registration for event {event_id} has ended for user {current_user.id}")
        raise HTTPException(status_code=403, detail="Registration for this event has ended")
    
    user_in_session = db.merge(current_user)
    if any(user.id == user_in_session.id for user in event.participants):
        logger.info(f"User {user_in_session.id} already participating in event {event_id}")
        return {"message": "Already participating in this event"}
    event.participants.append(user_in_session)
    db.commit()
    logger.info(f"User {user_in_session.id} joined event {event_id}")
    return {"message": "Successfully joined the event"}

# Endpoint: POST /events/leave/{event_id}
# Description: Allows a user to leave an event by event_id.
@router.post("/leave/{event_id}", response_model=schemas.MessageResponse)
def leave_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) attempting to leave event {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for user {current_user.id}")
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Check if event registration is still open for leaving
    now = datetime.utcnow()
    if event.registration_end and now > event.registration_end:
        logger.error(f"Registration for event {event_id} has ended, cannot leave for user {current_user.id}")
        raise HTTPException(status_code=403, detail="Registration for this event has ended, cannot leave now")
    
    user_in_event = next((user for user in event.participants if user.id == current_user.id), None)
    if not user_in_event:
        logger.info(f"User {current_user.id} is not participating in event {event_id}")
        return {"message": "You are not participating in this event"}
    event.participants.remove(user_in_event)
    db.commit()
    logger.info(f"User {current_user.id} left event {event_id}")
    return {"message": "Successfully left the event"}

# Officer Endpoints (Manage Events)

# Endpoint: GET /events/officer/list
# Description: Fetches a list of all active (non-archived) events.
# Modified Endpoint: GET /events/officer/list
@router.get("/officer/list", response_model=List[schemas.EventSchema])
def admin_list_events(
    archived: bool = False,
    db: Session = Depends(get_db)
):
    logger.debug(f"Fetching events with archived={archived}")
    events = db.query(models.Event).filter(models.Event.archived == archived).all()
    logger.info(f"Fetched {len(events)} events with archived={archived}")
    return events

# Endpoint: POST /events/officer/create
# Description: Creates a new event. An image can be optionally uploaded to R2.
@router.post("/officer/create", response_model=schemas.EventSchema)
async def admin_create_event(
    title: str = Form(...),
    description: str = Form(...),
    date: datetime = Form(...),
    location: str = Form(""),
    registration_start: Optional[datetime] = Form(None),
    registration_end: Optional[datetime] = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    logger.debug(f"Creating event with title: {title}")
    
    image_url = None
    if image and image.filename:
        # Only attempt upload if there's actually a file
        # Generate a unique filename to prevent collisions
        filename = f"{uuid.uuid4()}-{image.filename}"
        object_key = f"event_images/{filename}"
        image_url = await upload_to_r2(image, object_key)
        logger.debug(f"Uploaded event image to R2: {image_url}")
    
    # Set default registration_start if not provided
    if not registration_start:
        registration_start = datetime.utcnow()
    
    new_event = models.Event(
        title=title,
        description=description,
        date=date,
        image_url=image_url,
        location=location,
        registration_start=registration_start,
        registration_end=registration_end
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    logger.info(f"Created event successfully with id: {new_event.id}")
    return new_event

# Endpoint: PUT /events/officer/update/{event_id}
# Description: Updates an existing event, including its image in R2.
@router.put("/officer/update/{event_id}", response_model=schemas.EventSchema)
async def admin_update_event(
    event_id: int,
    title: str = Form(...),
    description: str = Form(...),
    date: datetime = Form(...),
    location: str = Form(""),
    registration_start: Optional[datetime] = Form(None),
    registration_end: Optional[datetime] = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    logger.debug(f"Updating event id: {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for update")
        raise HTTPException(status_code=404, detail="Event not found")
    
    if image and image.filename:
        # Only attempt upload if there's actually a file
        # Generate a unique filename to prevent collisions
        filename = f"{uuid.uuid4()}-{image.filename}"
        object_key = f"event_images/{filename}"
        event.image_url = await upload_to_r2(image, object_key)
        logger.debug(f"Updated event image in R2: {event.image_url}")
    
    event.title = title
    event.description = description
    event.date = date
    event.location = location
    
    # Update registration dates if provided
    if registration_start:
        event.registration_start = registration_start
    if registration_end:
        event.registration_end = registration_end
        
    db.commit()
    db.refresh(event)
    logger.info(f"Updated event {event_id} successfully")
    return event

# Endpoint: DELETE /events/officer/delete/{event_id}
# Description: Archives an event.
@router.delete("/officer/delete/{event_id}", response_model=dict)
def admin_delete_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    logger.debug(f"Attempting to archive event id: {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Event not found")
    event.archived = True
    db.commit()
    logger.info(f"Archived event {event_id} successfully")
    return {"detail": "Event archived successfully"}

# Endpoint: GET /events/{event_id}/participants
# Description: Returns a list of users participating in the specified event.
@router.get("/{event_id}/participants", response_model=List[schemas.User])
def get_event_participants(
    event_id: int,
    db: Session = Depends(get_db)
):
    logger.debug(f"Fetching participants for event id: {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for fetching participants")
        raise HTTPException(status_code=404, detail="Event not found")
    logger.info(f"Fetched {len(event.participants)} participants for event id: {event_id}")
    return event.participants