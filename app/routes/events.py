import logging
from datetime import datetime
import os
from typing import List, Optional
import boto3
from botocore.client import Config
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from io import BytesIO
from PIL import Image
import fitz  # PyMuPDF

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_user, get_current_officer

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

logger.debug(f"CF_ACCESS_KEY_ID set: {bool(access_key_id)}")
logger.debug(f"CF_SECRET_ACCESS_KEY set: {bool(secret_access_key)}")
logger.debug(f"CLOUDFLARE_R2_BUCKET: {bucket_name}")
logger.debug(f"CLOUDFLARE_R2_ENDPOINT: {endpoint_url}")

if not bucket_name:
    logger.error("CLOUDFLARE_R2_BUCKET environment variable is not set")
    bucket_name = "specs-nexus-files"

s3 = boto3.client(
    's3',
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

async def upload_to_r2(file: UploadFile, object_key: str):
    try:
        access_key = os.getenv("CF_ACCESS_KEY_ID")
        secret_key = os.getenv("CF_SECRET_ACCESS_KEY")
        bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET")
        endpoint_url = os.getenv("CLOUDFLARE_R2_ENDPOINT")
        worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "https://specsnexus-images.senya-videos.workers.dev")
        
        logger.info(f"R2 Credentials - Access Key: {'Available' if access_key else 'Missing'}")
        logger.info(f"R2 Credentials - Secret Key: {'Available' if secret_key else 'Missing'}")
        logger.info(f"R2 Credentials - Bucket: {bucket_name or 'Missing'}")
        logger.info(f"R2 Credentials - Endpoint: {endpoint_url or 'Missing'}")
        logger.info(f"R2 Credentials - Worker URL: {worker_url or 'Missing'}")
        
        if not all([access_key, secret_key, bucket_name, endpoint_url, worker_url]):
            raise ValueError("Missing R2 credentials or configuration")
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )
        
        logger.info(f"Uploading file to R2: {object_key}")
        s3_client.upload_fileobj(file.file, bucket_name, object_key)
        
        if worker_url.endswith('/'):
            file_url = f"{worker_url}{object_key}"
        else:
            file_url = f"{worker_url}/{object_key}"
            
        logger.info(f"File uploaded successfully: {file_url}")
        return file_url
    except Exception as e:
        logger.error(f"Error uploading file to R2: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file to R2: {str(e)}")

async def generate_pdf_thumbnail(pdf_url: str, certificate_id: int) -> str:
    try:
        worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "https://specsnexus-images.senya-videos.workers.dev")
        # Extract object_key from pdf_url (e.g., remove worker URL prefix)
        if pdf_url.startswith(worker_url):
            object_key = pdf_url[len(worker_url):].lstrip('/')
        else:
            object_key = pdf_url.split('/')[-1]  # Fallback to last component
        thumbnail_key = f"thumbnails/{certificate_id}_{object_key.split('/')[-1]}.png"
        
        logger.info(f"Generating thumbnail for certificate {certificate_id}, object_key: {object_key}")
        
        # Check if thumbnail already exists
        try:
            s3.head_object(Bucket=bucket_name, Key=thumbnail_key)
            logger.info(f"Thumbnail already exists: {thumbnail_key}")
            return f"{worker_url}/{thumbnail_key}"
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] != '404':
                logger.error(f"Error checking thumbnail existence: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error checking thumbnail: {str(e)}")

        # Verify PDF exists
        try:
            s3.head_object(Bucket=bucket_name, Key=object_key)
        except s3.exceptions.ClientError as e:
            logger.error(f"PDF not found in R2: {object_key}, error: {str(e)}")
            raise HTTPException(status_code=404, detail=f"PDF not found in R2: {object_key}")

        # Fetch PDF
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        pdf_data = response['Body'].read()
        logger.info(f"PDF fetched successfully: {object_key}")

        # Open PDF with PyMuPDF
        pdf = fitz.open(stream=pdf_data, filetype="pdf")
        if len(pdf) == 0:
            logger.error(f"Invalid PDF for certificate {certificate_id}: No pages found")
            raise HTTPException(status_code=400, detail="Invalid PDF: No pages found")
        page = pdf[0]  # First page

        # Render page to pixmap
        pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))  # 150 DPI
        logger.info(f"PDF page rendered to pixmap: {pix.width}x{pix.height}")

        # Convert to Pillow image for resizing
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img = img.resize((280, 140), Image.Resampling.LANCZOS)

        # Save thumbnail to BytesIO
        img_buffer = BytesIO()
        img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        # Upload thumbnail to R2
        s3.upload_fileobj(img_buffer, bucket_name, thumbnail_key)
        logger.info(f"Thumbnail generated and uploaded: {thumbnail_key}")

        return f"{worker_url}/{thumbnail_key}"
    except Exception as e:
        logger.error(f"Error generating thumbnail for certificate {certificate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF thumbnail: {str(e)}")

# Endpoint: GET /events/
@router.get("/", response_model=List[schemas.EventSchema])
def get_events(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) fetching all active events")
    events = db.query(models.Event).filter(models.Event.archived == False).all()
    
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

@router.get("/officer/list", response_model=List[schemas.EventSchema])
def admin_list_events(
    archived: bool = False,
    db: Session = Depends(get_db),
):
    events = db.query(models.Event).filter(models.Event.archived == archived).all()
    logger.info(f"Fetched {len(events)} events with archived={archived}")
    return events

@router.post("/officer/create", response_model=schemas.EventSchema)
async def admin_create_event(
    title: str = Form(...),
    description: str = Form(...),
    date: datetime = Form(...),
    location: str = Form(""),
    registration_start: Optional[datetime] = Form(None),
    registration_end: Optional[datetime] = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    
):
    logger.debug(f"Officer creating event with title: {title}")
    
    image_url = None
    if image and image.filename:
        filename = f"{uuid.uuid4()}-{image.filename}"
        object_key = f"event_images/{filename}"
        image_url = await upload_to_r2(image, object_key)
        logger.debug(f"Uploaded event image to R2: {image_url}")
    
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
    logger.info(f"Officer {current_officer.id} created event successfully with id: {new_event.id}")
    return new_event

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
    db: Session = Depends(get_db),
    
):
    logger.debug(f"Officer updating event id: {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for update")
        raise HTTPException(status_code=404, detail="Event not found")
    
    if image and image.filename:
        filename = f"{uuid.uuid4()}-{image.filename}"
        object_key = f"event_images/{filename}"
        event.image_url = await upload_to_r2(image, object_key)
        logger.debug(f"Updated event image in R2: {event.image_url}")
    
    event.title = title
    event.description = description
    event.date = date
    event.location = location
    
    if registration_start:
        event.registration_start = registration_start
    if registration_end:
        event.registration_end = registration_end
        
    db.commit()
    db.refresh(event)
    logger.info(f"Officer {current_officer.id} updated event {event_id} successfully")
    return event

@router.delete("/officer/delete/{event_id}", response_model=dict)
def admin_delete_event(
    event_id: int,
    db: Session = Depends(get_db),
   
):
    logger.debug(f"Officer attempting to archive event id: {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Event not found")
    event.archived = True
    db.commit()
    logger.info(f"Officer {current_officer.id} archived event {event_id} successfully")
    return {"detail": "Event archived successfully"}

@router.get("/{event_id}/participants", response_model=List[schemas.User])
def get_event_participants(
    event_id: int,
    db: Session = Depends(get_db),
    
):
    logger.debug(f"Officer fetching participants for event id: {event_id}")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found for fetching participants")
        raise HTTPException(status_code=404, detail="Event not found")
    logger.info(f"Fetched {len(event.participants)} participants for event id: {event_id}")
    return event.participants

@router.get("/{event_id}/certificates/{user_id}", response_model=schemas.ECertificateSchema)
def get_e_certificate(
    event_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    logger.debug(f"Officer fetching certificate for user {user_id} in event {event_id}")
    
    certificate = db.query(models.ECertificate).filter(
        models.ECertificate.event_id == event_id,
        models.ECertificate.user_id == user_id
    ).first()
    
    if not certificate:
        logger.error(f"No certificate found for user {user_id} in event {event_id}")
        raise HTTPException(status_code=404, detail="No certificate found for this user and event")
    
    certificate.event_title = certificate.event.title if certificate.event else "Unknown Event"
    logger.info(f"Fetched certificate for user {user_id} in event {event_id}")
    return certificate

@router.post("/{event_id}/certificates/{user_id}", response_model=schemas.ECertificateSchema)
async def upload_e_certificate(
    event_id: int,
    user_id: int,
    certificate: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    logger.debug(f"Officer uploading e-certificate for user {user_id} in event {event_id}")
    
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found")
        raise HTTPException(status_code=404, detail="Event not found")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger.error(f"User {user_id} not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    if not any(p.id == user_id for p in event.participants):
        logger.error(f"User {user_id} is not a participant in event {event_id}")
        raise HTTPException(status_code=403, detail="User is not a participant in this event")
    
    existing_certificate = db.query(models.ECertificate).filter(
        models.ECertificate.event_id == event_id,
        models.ECertificate.user_id == user_id
    ).first()
    
    filename = f"{uuid.uuid4()}-{certificate.filename}"
    object_key = f"e_certificates/{filename}"
    certificate_url = await upload_to_r2(certificate, object_key)
    
    # Generate thumbnail
    cert_id = existing_certificate.id if existing_certificate else uuid.uuid4()
    thumbnail_url = await generate_pdf_thumbnail(certificate_url, cert_id)
    
    if existing_certificate:
        # Update existing certificate
        existing_certificate.certificate_url = certificate_url
        existing_certificate.thumbnail_url = thumbnail_url
        existing_certificate.file_name = certificate.filename
        existing_certificate.issued_date = datetime.utcnow()
        db.commit()
        db.refresh(existing_certificate)
        existing_certificate.event_title = event.title
        logger.info(f"E-certificate updated for user {user_id} in event {event_id}")
        return existing_certificate
    else:
        # Create new certificate
        new_certificate = models.ECertificate(
            user_id=user_id,
            event_id=event_id,
            certificate_url=certificate_url,
            thumbnail_url=thumbnail_url,
            file_name=certificate.filename,
            issued_date=datetime.utcnow()
        )
        db.add(new_certificate)
        db.commit()
        db.refresh(new_certificate)
        new_certificate.event_title = event.title
        logger.info(f"E-certificate uploaded for user {user_id} in event {event_id}")
        return new_certificate

@router.get("/certificates", response_model=List[schemas.ECertificateSchema])
def get_user_certificates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} fetching their e-certificates")
    certificates = db.query(models.ECertificate).join(models.Event).filter(
        models.ECertificate.user_id == current_user.id
    ).all()
    
    for cert in certificates:
        cert.event_title = cert.event.title if cert.event else "Unknown Event"
    
    logger.info(f"User {current_user.id} fetched {len(certificates)} e-certificates")
    return certificates

@router.get("/certificates/{certificate_id}/thumbnail", response_model=str)
async def get_certificate_thumbnail(
    certificate_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} fetching thumbnail for certificate {certificate_id}")
    certificate = db.query(models.ECertificate).filter(
        models.ECertificate.id == certificate_id,
        models.ECertificate.user_id == current_user.id
    ).first()
    
    if not certificate:
        logger.error(f"No certificate found for id {certificate_id} and user {current_user.id}")
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    if not certificate.certificate_url:
        logger.error(f"No certificate URL for certificate {certificate_id}")
        raise HTTPException(status_code=400, detail="No certificate URL available")
    
    if not certificate.thumbnail_url:
        # Generate thumbnail if it doesn't exist
        certificate.thumbnail_url = await generate_pdf_thumbnail(certificate.certificate_url, certificate_id)
        db.commit()
        db.refresh(certificate)
    
    logger.info(f"Thumbnail fetched for certificate {certificate_id}")
    return certificate.thumbnail_url
