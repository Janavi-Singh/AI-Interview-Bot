import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGO_URI)
db = client["InterviewBotDB"] 

jobs_collection = db["jobs"]
candidates_collection = db["candidates"]
interviews_collection = db["interviews"]

def get_db():
    return db