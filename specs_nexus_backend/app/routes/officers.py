import logging
from datetime import timedelta
from typing import List

from fastapi import APIRouter, HTTPException, Depends, Form, UploadFile, File
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import admin_required, create_access_token

logger = logging.getLogger("app.officers")

router = APIRouter(prefix="/officers", tags=["Officers"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Officer Authentication Endpoints

# Endpoint: POST /officers/login
# Description: Authenticates an officer using email and password, and returns a JWT token along with officer details.
@router.post("/login", response_model=schemas.TokenResponse)
def officer_login(officer: schemas.OfficerLoginSchema, db: Session = Depends(get_db)):
    logger.debug(f"Officer login attempt for email: {officer.email}")
    db_officer = db.query(models.Officer).filter(models.Officer.email == officer.email).first()
    if not db_officer:
        logger.error("Incorrect email provided for officer login")
        raise HTTPException(status_code=400, detail="Incorrect email")
    
    if officer.password != db_officer.password:
        logger.error("Incorrect password for officer login")
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(data={"sub": str(db_officer.id)}, expires_delta=access_token_expires)
    logger.info(f"Officer {db_officer.id} ({db_officer.full_name}) logged in successfully")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "officer": db_officer
    }

# Endpoint: GET /officers/
# Description: Returns a list of all officers for a logged-in officer.
@router.get("/", response_model=List[schemas.OfficerSchema])
def get_officers(db: Session = Depends(get_db), current_officer: models.Officer = Depends(admin_required)):
    logger.debug(f"get_officers called by Officer {current_officer.id} ({current_officer.full_name})")
    officers = db.query(models.Officer).all()
    logger.info(f"Officer {current_officer.id} fetched {len(officers)} officers")
    return officers

# Endpoint: GET /officers/ (Admin)
# Description: Allows an admin to fetch all officers.
@router.get("/", response_model=List[schemas.OfficerSchema], dependencies=[Depends(admin_required)])
def get_officers_admin(db: Session = Depends(get_db)):
    logger.debug("Admin fetching all officers")
    officers = db.query(models.Officer).all()
    logger.info(f"Admin fetched {len(officers)} officers")
    return officers

# Endpoint: GET /officers/users
# Description: Allows an admin to fetch all users for adding as officers.
@router.get("/users", response_model=List[schemas.User], dependencies=[Depends(admin_required)])
def get_users_for_officers(db: Session = Depends(get_db)):
    logger.debug("Admin fetching all users for officer creation")
    users = db.query(models.User).all()
    logger.info(f"Admin fetched {len(users)} users")
    return users

# Endpoint: POST /officers/bulk
# Description: Allows an admin to create multiple officer accounts from selected user IDs.
@router.post("/bulk", response_model=List[schemas.OfficerSchema], dependencies=[Depends(admin_required)])
def create_officers_bulk(
    user_ids: List[int] = Form(...),
    position: str = Form(...),
    db: Session = Depends(get_db)
):
    logger.debug(f"Admin creating officers from user IDs: {user_ids}")
    created_officers = []
    for user_id in user_ids:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            logger.warning(f"User with ID {user_id} not found, skipping")
            continue
        existing_officer = db.query(models.Officer).filter(
            (models.Officer.email == user.email) | (models.Officer.student_number == user.student_number)
        ).first()
        if existing_officer:
            logger.warning(f"Officer with email {user.email} or student number {user.student_number} already exists, skipping")
            continue
        officer = models.Officer(
            full_name=user.full_name,
            email=user.email,
            password=user.password,
            student_number=user.student_number,
            year=user.year,
            block=user.block,
            position=position,
            archived=False
        )
        db.add(officer)
        created_officers.append(officer)
    db.commit()
    for officer in created_officers:
        db.refresh(officer)
    logger.info(f"Created {len(created_officers)} officers successfully")
    return created_officers

# Endpoint: POST /officers/
# Description: Allows an admin to create a new officer account.
@router.post("/", response_model=schemas.OfficerSchema, dependencies=[Depends(admin_required)])
def create_officer(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    student_number: str = Form(...),
    year: str = Form(...),
    block: str = Form(...),
    position: str = Form(...),
    db: Session = Depends(get_db)
):
    logger.debug(f"Admin creating officer with email: {email}")
    existing = db.query(models.Officer).filter(
        (models.Officer.email == email) | (models.Officer.student_number == student_number)
    ).first()
    if existing:
        logger.error("Officer with this email or student number already exists")
        raise HTTPException(status_code=400, detail="Officer with this email or student number already exists")
    
    officer = models.Officer(
        full_name=full_name,
        email=email,
        password=password,
        student_number=student_number,
        year=year,
        block=block,
        position=position,
        archived=False
    )
    db.add(officer)
    db.commit()
    db.refresh(officer)
    logger.info(f"Officer created successfully with id: {officer.id}")
    return officer

# Endpoint: PUT /officers/{officer_id}
# Description: Allows an admin to update an existing officer's details.
@router.put("/{officer_id}", response_model=schemas.OfficerSchema, dependencies=[Depends(admin_required)])
def update_officer(
    officer_id: int,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    student_number: str = Form(...),
    year: str = Form(...),
    block: str = Form(...),
    position: str = Form(...),
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(admin_required)
):
    logger.debug(f"Officer {current_officer.id} ({current_officer.full_name}) updating officer id: {officer_id}")
    officer = db.query(models.Officer).filter(models.Officer.id == officer_id).first()
    if not officer:
        logger.error("Officer not found for update")
        raise HTTPException(status_code=404, detail="Officer not found")
    officer.full_name = full_name
    officer.email = email
    officer.password = password
    officer.student_number = student_number
    officer.year = year
    officer.block = block
    officer.position = position
    db.commit()
    db.refresh(officer)
    logger.info(f"Officer {officer_id} updated successfully by Officer {current_officer.id}")
    return officer

# Endpoint: DELETE /officers/{officer_id}
# Description: Permanently deletes an officer account.
@router.delete("/{officer_id}", response_model=dict, dependencies=[Depends(admin_required)])
def delete_officer(officer_id: int, db: Session = Depends(get_db), current_officer: models.Officer = Depends(admin_required)):
    logger.debug(f"Officer {current_officer.id} ({current_officer.full_name}) deleting officer id: {officer_id}")
    officer = db.query(models.Officer).filter(models.Officer.id == officer_id).first()
    if not officer:
        logger.error("Officer not found for deletion")
        raise HTTPException(status_code=404, detail="Officer not found")
    db.delete(officer)
    db.commit()
    logger.info(f"Officer {officer_id} deleted successfully by Officer {current_officer.id}")
    return {"detail": "Officer deleted successfully"}

