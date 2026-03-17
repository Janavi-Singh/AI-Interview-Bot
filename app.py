"""
AI Interview Bot - Main Server
Connects Email Automation + Link Manager + Dashboard
"""

from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
from pymongo import MongoClient
from email_automation import send_interview_email, send_bulk_emails
from link_manager import validate_link, mark_link_used, expire_old_links
from config import MONGO_URI, DB_NAME, INTERVIEWS_COLLECTION
import os

app = Flask(__name__)


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


@app.route("/")
def dashboard():
    with open("dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


# ── Dashboard API ─────────────────────────────────
@app.route("/api/dashboard")
def dashboard_api():
    """Returns all interview data for dashboard"""
    try:
        expire_old_links()
        db = get_db()
        interviews = list(db[INTERVIEWS_COLLECTION].find(
            {}, {"_id": 0}
        ).sort("created_at", -1))

        # Convert datetime to string for JSON
        for interview in interviews:
            if interview.get("created_at"):
                interview["created_at"]   = str(interview["created_at"])
            if interview.get("expires_at"):
                interview["expires_at"]   = str(interview["expires_at"])
            if interview.get("email_sent_at"):
                interview["email_sent_at"] = str(interview["email_sent_at"])

        return jsonify({"interviews": interviews, "total": len(interviews)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Send Single Email ─────────────────────────────
@app.route("/api/send-email", methods=["POST"])
def send_email_route():
    """
    Sends interview email to a single candidate.
    Body: { name, email, job_id }
    """
    data = request.json
    name   = data.get("name")
    email  = data.get("email")
    job_id = data.get("job_id", "default")

    if not name or not email:
        return jsonify({"error": "name and email required"}), 400

    result = send_interview_email(name, email, job_id)

    if result:
        return jsonify({"success": True, "message": f"Email sent to {email}"})
    else:
        return jsonify({"success": False, "message": "Email failed - check config.py"}), 500


# ── Send Bulk Emails ──────────────────────────────
@app.route("/api/send-bulk", methods=["POST"])
def send_bulk_route():
    """
    Sends emails to multiple candidates.
    Body: { job_id, candidates: [{name, email}] }
    """
    data       = request.json
    job_id     = data.get("job_id", "default")
    candidates = data.get("candidates", [])

    if not candidates:
        return jsonify({"error": "candidates list required"}), 400

    send_bulk_emails(candidates, job_id)
    return jsonify({"success": True, "message": f"Processed {len(candidates)} candidates"})


# ── Validate Interview Link ───────────────────────
@app.route("/interview/<token>")
def interview_route(token):
    """Validates interview link and starts interview"""
    result = validate_link(token)

    if not result["valid"]:
        return f"""
        <html><body style='font-family:Arial;text-align:center;padding:50px;'>
            <h2 style='color:#e74c3c;'>❌ Link Invalid</h2>
            <p>{result['reason']}</p>
        </body></html>
        """

    return f"""
    <html><body style='font-family:Arial;text-align:center;padding:50px;'>
        <h2 style='color:#27ae60;'>✅ Welcome, {result['candidate_name']}!</h2>
        <p>Your interview is starting...</p>
        <p style='color:#888;font-size:13px;'>
            Link expires: {result['expires_at']}
        </p>
    </body></html>
    """


# ── Mark Interview Complete ───────────────────────
@app.route("/api/complete/<token>", methods=["POST"])
def complete_interview(token):
    """Marks interview as completed"""
    mark_link_used(token)
    return jsonify({"success": True})


if __name__ == "__main__":
    print("=" * 50)
    print("  AI Interview Bot - Email Automation Server")
    print("=" * 50)
    print("  Dashboard: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
