"""
AI Interview Bot - Email Automation
Sends personalized interview emails to candidates automatically.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pymongo import MongoClient
from link_manager import generate_interview_link
from config import (
    EMAIL_ADDRESS, EMAIL_PASSWORD,
    EMAIL_HOST, EMAIL_PORT,
    MONGO_URI, DB_NAME, INTERVIEWS_COLLECTION
)


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


def build_email_body(candidate_name: str, interview_link: str, expires_at: datetime) -> str:
    """Builds personalized HTML email body"""
    expiry_str = expires_at.strftime("%B %d, %Y at %I:%M %p")
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px;">

        <h2 style="color: #2c3e50;">Interview Invitation</h2>

        <p>Dear <strong>{candidate_name}</strong>,</p>

        <p>Congratulations! We have reviewed your application and would like to invite you
        to complete an AI-powered interview for the position you applied for.</p>

        <h3>How to Attend:</h3>
        <ol>
            <li>Click the interview link below</li>
            <li>Verify your identity with your email</li>
            <li>The AI interviewer will guide you through the questions</li>
            <li>Answer each question clearly and completely</li>
        </ol>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{interview_link}"
               style="background-color: #3498db; color: white; padding: 15px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Start Interview
            </a>
        </div>

        <p style="color: #e74c3c;">
            ⚠️ <strong>Important:</strong> This link will expire on <strong>{expiry_str}</strong>.
            Please complete your interview before this time.
        </p>

        <p>If the button doesn't work, copy and paste this link:</p>
        <p style="color: #3498db;">{interview_link}</p>

        <hr>
        <p style="color: #888; font-size: 12px;">
            This is an automated email. Please do not reply to this email.
        </p>

    </body>
    </html>
    """


def send_interview_email(candidate_name: str, candidate_email: str, job_id: str) -> bool:
    """
    Main function - generates link and sends interview email.
    Call this after resume upload.
    """
    print(f"\n[Email] Processing: {candidate_name} ({candidate_email})")

    # Step 1 - Generate unique interview link
    link_data = generate_interview_link(candidate_email, candidate_name, job_id)
    interview_link = link_data["interview_link"]
    expires_at     = link_data["expires_at"]
    token          = link_data["token"]

    # Step 2 - Build email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your AI Interview Invitation"
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = candidate_email

    html_body = build_email_body(candidate_name, interview_link, expires_at)
    msg.attach(MIMEText(html_body, "html"))

    # Step 3 - Send email
    try:
        print(f"[Email] Connecting to Gmail SMTP...")
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, candidate_email, msg.as_string())
        server.quit()

        # Step 4 - Update DB - mark email sent
        db = get_db()
        db[INTERVIEWS_COLLECTION].update_one(
            {"token": token},
            {"$set": {
                "email_sent"    : True,
                "email_sent_at" : datetime.now()
            }}
        )

        print(f"[Email] ✅ Sent to {candidate_email}")
        print(f"[Email] Link: {interview_link}")
        print(f"[Email] Expires: {expires_at}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[Email] ❌ Authentication failed - Check EMAIL_ADDRESS and EMAIL_PASSWORD in config.py")
        return False
    except Exception as e:
        print(f"[Email] ❌ Failed: {e}")
        return False


def send_bulk_emails(candidates: list, job_id: str):
    """
    Sends interview emails to multiple candidates.
    Called after bulk resume upload.
    candidates = [{"name": "John", "email": "john@example.com"}, ...]
    """
    print(f"\n[Email] Sending to {len(candidates)} candidate(s)...")
    print("=" * 50)

    success = 0
    failed  = 0

    for candidate in candidates:
        result = send_interview_email(
            candidate_name  = candidate["name"],
            candidate_email = candidate["email"],
            job_id          = job_id
        )
        if result:
            success += 1
        else:
            failed += 1

    print("=" * 50)
    print(f"[Email] Done! ✅ Sent: {success} | ❌ Failed: {failed}")
