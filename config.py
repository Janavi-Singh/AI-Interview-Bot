"""
AI Interview Bot - Config
Phase 1 - Link Generation
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── MongoDB — same as main project ───────────────
MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME   = "InterviewBotDB"

# ── Collections — same as main project ───────────
CANDIDATES_COLLECTION  = "candidates"
INTERVIEWS_COLLECTION  = "interviews"
JOBS_COLLECTION        = "jobs"

# ── Interview Link Settings ───────────────────────
BASE_URL          = "http://localhost:5000"
LINK_EXPIRY_HOURS = 72

# ── Email Settings (fill when Gmail ready) ────────
EMAIL_ADDRESS  = os.getenv("EMAIL_ADDRESS", "your-email@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your-app-password")
EMAIL_HOST     = "smtp.gmail.com"
EMAIL_PORT     = 587
