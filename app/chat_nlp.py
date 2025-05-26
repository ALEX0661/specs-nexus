# chat_nlp.py
import os
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
from app.database import SessionLocal
from app import models
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def fetch_events(db):
    """Fetch all active events from the database with participation status."""
    try:
        events = db.query(models.Event).filter(models.Event.archived == False).all()
        current_user_id = getattr(db.query(models.User).filter_by(id=1).first(), 'id', None)  # Example user ID; adjust dynamically
        return [
            {
                "title": event.title,
                "description": event.description,
                "date": event.date.isoformat(),
                "location": event.location,
                "registration_start": event.registration_start.isoformat() if event.registration_start else None,
                "registration_end": event.registration_end.isoformat() if event.registration_end else None,
                "is_participant": any(participant.id == current_user_id for participant in event.participants)
            } for event in events
        ]
    except Exception as e:
        return f"Error fetching events"

def fetch_announcements(db):
    """Fetch all active announcements from the database."""
    try:
        announcements = db.query(models.Announcement).filter(models.Announcement.archived == False).all()
        return [
            {"title": announcement.title, "description": announcement.description, "date": announcement.date.isoformat(), "location": announcement.location}
            for announcement in announcements
        ]
    except Exception as e:
        return f"Error fetching announcements"

def fetch_clearances(db, user_id):
    """Fetch clearance details for a user from the database."""
    try:
        clearances = db.query(models.Clearance).filter(models.Clearance.user_id == user_id, models.Clearance.archived == False).all()
        return [
            {
                "id": clearance.id,
                "requirement": clearance.requirement,
                "amount": clearance.amount,
                "payment_status": clearance.payment_status,
                "status": clearance.status,
                "payment_method": clearance.payment_method,
                "payment_date": clearance.payment_date.isoformat() if clearance.payment_date else None,
                "approval_date": clearance.approval_date.isoformat() if clearance.approval_date else None,
                "denial_reason": clearance.denial_reason
            } for clearance in clearances
        ]
    except Exception as e:
        return f"Error fetching clearances"

def fetch_officers(db):
    """Fetch all active officers from the database."""
    try:
        officers = db.query(models.Officer).filter(models.Officer.archived == False).all()
        return [{"full_name": officer.full_name, "position": officer.position} for officer in officers]
    except Exception as e:
        return f"Error fetching officers"

def get_chat_response(user_query: str, user_id: int) -> str:
    """
    Generates a response to a user query using the Hugging Face Inference API.
    Args:
        user_query (str): The user's input query.
        user_id (int): The ID of the user making the query.
    Returns:
        str: The generated response or an error message.
    """
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    logger.info(f"Hugging Face API Key loaded: {'Yes' if api_key else 'No'}")
    if not api_key:
        raise ValueError("HUGGINGFACE_API_KEY environment variable not set")

    db = SessionLocal()
    try:
        events = fetch_events(db)
        announcements = fetch_announcements(db)
        clearances = fetch_clearances(db, user_id)
        officers = fetch_officers(db)
    finally:
        db.close()

    events_str = "\n".join([
        f"## {event['title']}\n"
        f"  - Description: {event['description']}\n"
        f"  - Date: {event['date']}\n"
        f"  - Location: {event['location']}\n"
        f"  - Registration Start: {event['registration_start'] or 'Not specified'}\n"
        f"  - Registration End: {event['registration_end'] or 'Not specified'}\n"
        f"  - Registered: {'Yes' if event['is_participant'] else 'No'}"
        for event in events
    ]) if isinstance(events, list) else str(events)

    announcements_str = "\n".join([
        f"## {ann['title']}\n"
        f"  - Description: {ann['description']}\n"
        f"  - Date: {ann['date']}\n"
        f"  - Location: {ann['location']}"
        for ann in announcements
    ]) if isinstance(announcements, list) else str(announcements)

    clearances_str = "\n".join([
        f"## Clearance {c['id']}\n"
        f"  - Requirement: {c['requirement']}\n"
        f"  - Amount: {c['amount']}\n"
        f"  - Payment Status: {c['payment_status']}\n"
        f"  - Status: {c['status']}\n"
        f"  - Payment Method: {c['payment_method'] or 'None'}\n"
        f"  - Payment Date: {c['payment_date'] or 'None'}\n"
        f"  - Approval Date: {c['approval_date'] or 'None'}\n"
        f"  - Denial Reason: {c['denial_reason'] or 'None'}"
        for c in clearances
    ]) if isinstance(clearances, list) else str(clearances)

    officers_str = "\n".join([f"- **{o['full_name']}**: {o['position']}" for o in officers]) if isinstance(officers, list) else str(officers)

    full_prompt = (
        "You are SPECS NEXUS Assistance, a helpful chatbot for the SPECS Nexus platform, designed for the Society of Programming Enthusiasts in Computer Science (SPECS) at Gordon College. SPECS is a student organization under the College of Computer Studies (CCS) department, dedicated to fostering learning, innovation, and community involvement in computer science, specifically for the Bachelor of Science in Computer Science (BSCS) program. SPECS Nexus streamlines membership registration, event participation, and announcement updates, helping members stay connected and informed in a user-friendly environment. The platform has five main pages: Dashboard, Profile, Events, Announcements, and Membership. Below are details about each:\n\n"
        "**Dashboard Page**: The central hub where users can view their current requirements and clearance status, including an overview of pending tasks.\n\n"
        "**Profile Page**: Displays all personal details, providing a snapshot of the user's account information.\n\n"
        "**Events Page**: Lists all current SPECS events with details. Users can browse and choose to participate.\n\n"
        "**Announcements Page**: The source for SPECS updates and news.\n\n"
        "**Membership Page**: Shows clearance status and payment history. Users can view clearance details and payment progress. Payment options include GCash and PayMaya. After payment, users upload a digital receipt, and the system updates the status to 'Verifying' while an officer reviews it. If verified, the status changes to 'Clear'; otherwise, it remains 'Not Yet Cleared'.\n\n"
        "**Payment Methods**: GCash and PayMaya.\n\n"
        "**Current Events**:\n" + (events_str if events_str else "No events available.") + "\n\n"
        "**Current Announcements**:\n" + (announcements_str if announcements_str else "No announcements available.") + "\n\n"
        "**User Clearances**:\n" + (clearances_str if clearances_str else "No clearances available.") + "\n\n"
        "**Current Officers**:\n" + (officers_str if officers_str else "No officers available.") + "\n\n"
        "Instructions for responses:\n"
        "- Format responses using markdown-like formatting.\n"
        "- For events, use a heading (##) for each event title, followed by indented bullet points (  -) for details (Description, Date, Location, Registration Start, Registration End, Registered).\n"
        "- For clearances, use a heading (##) for each Clearance followed by the ID (e.g., Clearance 123), followed by indented bullet points for details (Requirement, Amount, Payment Status, Status, Payment Method, Payment Date, Approval Date, Denial Reason).\n"
        "- For announcements, use a heading (##) for each announcement title, followed by indented bullet points for details (Description, Date, Location).\n"
        "- For officer queries, list officers with their full name and position in a bullet-point list (e.g., - **Name**: Position).\n"
        "- If you lack specific information to answer a query, respond with: 'I'm sorry, I do not have that information.'\n"
        "- Ensure responses are concise and easy to read with clear section headings and spacing.\n\n"
        f"User Query: {user_query}\n"
        "Answer:"
    )

    client = InferenceClient(model="mistralai/Mixtral-8x7B-Instruct-v0.1", token=api_key)

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_query}
            ],
            max_tokens=512,
            temperature=0.7
        )
        logger.info("Successfully received response from Hugging Face API")
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Failed to get response from Hugging Face API")
        return f"Error: Failed to get response from API"