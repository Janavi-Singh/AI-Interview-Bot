"""
AI Interview Bot - Link Manager
Phase 1 - Unique interview link generation with 72hr expiry
Connects to same MongoDB as main project (InterviewBotDB)
"""

import uuid
from datetime import datetime, timedelta
from pymongo import MongoClient
from config import MONGO_URI, DB_NAME, INTERVIEWS_COLLECTION, BASE_URL, LINK_EXPIRY_HOURS


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


def generate_interview_link(candidate_email: str, candidate_name: str, job_id: str) -> dict:
    """
    Generates a unique interview link for a candidate.
    Link expires after 72 hours.
    Saves to InterviewBotDB → interviews collection.
    """
    # Generate unique token
    token = str(uuid.uuid4())

    # Set expiry time
    created_at = datetime.now()
    expires_at = created_at + timedelta(hours=LINK_EXPIRY_HOURS)

    # Build interview link
    interview_link = f"{BASE_URL}/interview/{token}"

    # Save to MongoDB — interviews collection
    db = get_db()
    interview_data = {
        "token"           : token,
        "candidate_email" : candidate_email,
        "candidate_name"  : candidate_name,
        "job_id"          : job_id,
        "interview_link"  : interview_link,
        "status"          : "pending",
        "created_at"      : created_at,
        "expires_at"      : expires_at,
        "email_sent"      : False,
        "email_sent_at"   : None,
    }
    db[INTERVIEWS_COLLECTION].insert_one(interview_data)

    print(f"[Link] ✅ Generated for: {candidate_name}")
    print(f"[Link] 🔗 Link: {interview_link}")
    print(f"[Link] ⏰ Expires: {expires_at}")

    return {
        "token"          : token,
        "interview_link" : interview_link,
        "expires_at"     : expires_at,
    }


def validate_link(token: str) -> dict:
    """
    Validates if interview link is still active.
    Returns status and candidate details.
    """
    db = get_db()
    interview = db[INTERVIEWS_COLLECTION].find_one({"token": token})

    if not interview:
        return {"valid": False, "reason": "Link not found"}

    # Check if expired
    if datetime.now() > interview["expires_at"]:
        db[INTERVIEWS_COLLECTION].update_one(
            {"token": token},
            {"$set": {"status": "expired"}}
        )
        return {"valid": False, "reason": "Link has expired"}

    if interview["status"] == "completed":
        return {"valid": False, "reason": "Interview already completed"}

    return {
        "valid"           : True,
        "candidate_name"  : interview["candidate_name"],
        "candidate_email" : interview["candidate_email"],
        "job_id"          : interview["job_id"],
        "expires_at"      : interview["expires_at"],
    }


def mark_link_used(token: str):
    """Marks interview as completed"""
    db = get_db()
    db[INTERVIEWS_COLLECTION].update_one(
        {"token": token},
        {"$set": {"status": "completed"}}
    )
    print(f"[Link] ✅ Token {token[:8]}... marked as completed")


def expire_old_links():
    """Marks all expired links automatically"""
    db = get_db()
    now = datetime.now()
    result = db[INTERVIEWS_COLLECTION].update_many(
        {"status": "pending", "expires_at": {"$lt": now}},
        {"$set": {"status": "expired"}}
    )
    if result.modified_count > 0:
        print(f"[Link] ⏰ Auto expired {result.modified_count} link(s)")
