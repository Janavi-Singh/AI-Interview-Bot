import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587

def build_email_body(candidate_name: str, interview_link: str, expires_at: datetime) -> str:
    """Builds personalized HTML email body"""
    expiry_str = expires_at.strftime("%B %d, %Y at %I:%M %p")
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px;">
        <h2 style="color: #2c3e50;">Interview Invitation - Hiringhood</h2>
        <p>Dear <strong>{candidate_name}</strong>,</p>
        <p>Congratulations! We have reviewed your application and would like to invite you
        to complete an AI-powered interview for the position you applied for.</p>
        
        <h3>How to Attend:</h3>
        <ol>
            <li>Click the interview link below</li>
            <li>Ensure you are in a quiet room with a working microphone</li>
            <li>The AI interviewer (Tara) will guide you through the questions</li>
            <li>Answer each question clearly and completely</li>
        </ol>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{interview_link}"
               style="background-color: #2563eb; color: white; padding: 15px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px; font-weight: bold;">
                Start Interview
            </a>
        </div>

        <p style="color: #e74c3c;">
            ⚠️ <strong>Important:</strong> This link will expire on <strong>{expiry_str}</strong>.
            Please complete your interview before this time.
        </p>

        <p>If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="color: #3498db;">{interview_link}</p>

        <hr>
        <p style="color: #888; font-size: 12px;">
            This is an automated email from Hiringhood. Please do not reply to this email.
        </p>
    </body>
    </html>
    """

def send_interview_email(candidate_name: str, candidate_email: str, interview_link: str, session_id: str, db_collection):
    """Sends the email in the background and updates MongoDB."""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("[Email] ❌ Missing EMAIL_ADDRESS or EMAIL_PASSWORD in .env")
        return

    print(f"\n[Email] Preparing invitation for: {candidate_name} ({candidate_email})")

    # Set expiry for 72 hours from now
    expires_at = datetime.now() + timedelta(hours=72)
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your AI Interview Invitation - Hiringhood"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = candidate_email

    html_body = build_email_body(candidate_name, interview_link, expires_at)
    msg.attach(MIMEText(html_body, "html"))

    try:
        print(f"[Email] Connecting to Gmail SMTP...")
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, candidate_email, msg.as_string())
        server.quit()

        # Update the main MongoDB record to show the email was sent
        db_collection.update_one(
            {"sessionId": session_id},
            {"$set": {
                "email_sent": True,
                "email_sent_at": datetime.now().isoformat(),
                "expires_at": expires_at.isoformat()
            }}
        )

        print(f"[Email] ✅ Successfully sent to {candidate_email}")
        
    except Exception as e:
        print(f"[Email] ❌ Failed to send email to {candidate_email}: {e}")
