from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect,BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from parsers import extract_text
from ai_engine import parse_jd, parse_resume, generate_question_pool, evaluate_candidate_answer, generate_interview_report
import json
from database import jobs_collection, candidates_collection, interviews_collection
from audio_utils import synthesize_speech
from stt_utils import StreamingAudioProcessor
from datetime import datetime
import asyncio
import base64
import os
import threading
from fastapi.responses import HTMLResponse
from email_automation import send_interview_email
app = FastAPI(title="AI Interview Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/prepare-interview/")
async def prepare_interview_session(
    background_tasks: BackgroundTasks,
    js_id: str = Form(...),
    contest_id: str = Form(...),
    recruiter_id: str = Form(...),
    resume_file: UploadFile = File(...),
    jd_file: UploadFile = File(...)
):
    try:
        resume_bytes = await resume_file.read()
        jd_bytes = await jd_file.read()
        resume_text = await extract_text(resume_bytes, resume_file.filename)
        jd_text = await extract_text(jd_bytes, jd_file.filename)
        
        parsed_jd = parse_jd(jd_text, contest_id)
        jobs_collection.update_one(
            {"_id": contest_id}, 
            {"$set": {"recruiter_id": recruiter_id, "jdContent": parsed_jd, "raw_jd_text": jd_text}}, 
            upsert=True
        )
        
        parsed_resume = parse_resume(resume_text, js_id)
        candidates_collection.update_one(
            {"_id": js_id}, 
            {"$set": {"profile": parsed_resume, "raw_resume_text": resume_text}}, 
            upsert=True
        )

        generated_questions = generate_question_pool(parsed_jd, parsed_resume)
        session_id = f"{js_id}_{contest_id}"
        interview_link = f"http://localhost:8000/test-interview/{session_id}"

        interviews_collection.update_one(
            {"sessionId": session_id},
            {"$set": {
                "job_id": contest_id, 
                "candidate_id": js_id,
                "generatedQuestions": generated_questions, 
                "asked_question_ids": [],
                "transcript": [], 
                "answers": [], 
                "scores": [], 
                "status": "pending",
                "email_sent": False # Track email status
            }}, 
            upsert=True
        )

        print(f"✅ INTERVIEW PREPARED: {session_id}")

        # --- NEW: TRIGGER BACKGROUND EMAIL ---
        # Safely extract name and email from Gemini's parsed JSON
        profile = parsed_resume.get("candidate_profile", {})
        candidate_name = profile.get("name", "Candidate")
        candidate_email = profile.get("email", "")

        # Basic validation to ensure an email was found before sending
        if candidate_email and "@" in candidate_email:
            background_tasks.add_task(
                send_interview_email,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                interview_link=interview_link,
                session_id=session_id,
                db_collection=interviews_collection
            )
        else:
            print(f"[Warning] No valid email found in resume for {candidate_name}. Invitation not sent.")

        return {
            "status": "success",
            "message": "JD, Resume, and Question Pool parsed successfully. Invitation email is being sent.",
            "data": {
                "session_id": session_id,
                "interview_link": interview_link,
                "candidate_email": candidate_email,
                "total_questions_generated": len(generated_questions)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ==========================================
# 2. GET INTERVIEW SESSION DETAILS & REPORT
# ==========================================
@app.get("/api/interview-session/{session_id}")
async def get_interview_session(session_id: str):
    try:
        doc = interviews_collection.find_one({"sessionId": session_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Interview session '{session_id}' not found.")
        
        doc.pop('_id', None)
        doc["interview_link"] = f"http://localhost:8000/test-interview/{session_id}"

        if doc.get("status") == "completed" and "final_report" not in doc:
            print(f"[API] Generating comprehensive final report for session {session_id}...")
            
            job_doc = jobs_collection.find_one({"_id": doc.get("job_id")})
            jd_context = job_doc.get("jdContent", {}) if job_doc else {}
            
            candidate_doc = candidates_collection.find_one({"_id": doc.get("candidate_id")})
            candidate_profile = candidate_doc.get("profile", {}) if candidate_doc else {}
            
            raw_transcript = doc.get("transcript", [])
            answers_data = doc.get("answers", [])
            
            qa_pairs = []
            scores = []
            
            current_q = None
            answer_index = 0
            
            # Step through the raw transcript to get the exact spoken conversation
            for entry in raw_transcript:
                if entry.get("speaker") == "interviewer":
                    current_q = entry.get("text")
                elif entry.get("speaker") == "candidate" and current_q:
                    ans_text = entry.get("text")
                    
                    score = 0
                    q_origin = "Pre-planned" # Default assumption
                    
                    # Match with the answers array to get the score and the ID
                    if answer_index < len(answers_data):
                        score = answers_data[answer_index].get("score", 0)
                        q_id = str(answers_data[answer_index].get("question_id", ""))
                        
                        # If the ID starts with 'dyn_', we know it was generated on the fly!
                        if q_id.startswith("dyn_"):
                            q_origin = "Dynamic Follow-up"
                            
                        answer_index += 1
                        
                    scores.append(score)
                    qa_pairs.append({
                        "question": current_q,
                        "answer": ans_text,
                        "score": score,
                        "origin": q_origin # Added the new origin flag!
                    })
                    
                    current_q = None 
                
            avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
            
            # Send the tagged Q&A to Mistral for analysis
            ai_analysis = generate_interview_report(jd_context, candidate_profile, qa_pairs, avg_score)
            
            final_report = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "interviewer": "Tara (Senior Technical Interviewer)",
                "interview_statistics": {
                    "total_questions": len(qa_pairs),
                    "overall_score": avg_score
                },
                "ai_analysis": ai_analysis,
                "detailed_qa": qa_pairs # This now contains the exact text and the origin flags
            }
            
            interviews_collection.update_one(
                {"sessionId": session_id},
                {"$set": {"final_report": final_report}}
            )
            
            doc["final_report"] = final_report

        return {"status": "success", "data": doc}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] Failed to fetch session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 3. LIVE INTERVIEW ROUTE (WEBSOCKET)
# ==========================================
active_connections = {}
MAX_QUESTIONS = 10

@app.websocket("/ws/interview/{session_id}")
async def interview_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    active_connections[session_id] = websocket
    loop = asyncio.get_running_loop()
    
    interview_doc = interviews_collection.find_one({"sessionId": session_id})
    if not interview_doc:
        await websocket.send_json({"type": "error", "message": "Session not found."})
        await websocket.close()
        return

    pool = interview_doc.get("generatedQuestions", [])
    asked_ids = interview_doc.get("asked_question_ids", [])
    current_question = pool[0] if not asked_ids else next((q for q in pool if q.get("id") == asked_ids[-1]), pool[0])
    
    processor = None

    async def on_interim(text: str):
        await websocket.send_json({"type": "interim_transcript", "text": text})

    async def process_final_answer(user_answer: str):
        nonlocal current_question
        
        if not user_answer:
            await websocket.send_json({"type": "info", "message": "I didn't hear anything clearly. Could you try answering again?"})
            return
            
        print(f"\n[Final Locked Transcript]: {user_answer}\n")
        await websocket.send_json({"type": "transcript_success", "text": "Answer logged securely. Evaluating..."})

        current_doc = interviews_collection.find_one({"sessionId": session_id})
        current_asked_ids = current_doc.get("asked_question_ids", [])
        
        pool_ids_asked = [i for i in current_asked_ids if not str(i).startswith("dyn_")]
        available_questions = [q for q in pool if q.get("id") not in pool_ids_asked]
        raw_transcript = current_doc.get("transcript", [])
        recent_context = "\n".join([f"{msg['speaker'].upper()}: {msg['text']}" for msg in raw_transcript[-4:]])

        evaluation = await asyncio.to_thread(
            evaluate_candidate_answer, current_question, user_answer, available_questions, recent_context
        )
        score_val = int(evaluation.get("score", 5))

        await asyncio.to_thread(
            interviews_collection.update_one,
            {"sessionId": session_id},
            {"$push": {
                "answers": {"question_id": current_question.get("id"), "text": user_answer, "score": score_val},
                "transcript": {"speaker": "candidate", "text": user_answer, "timestamp": datetime.utcnow().isoformat()}
            }}
        )

        if len(current_asked_ids) >= MAX_QUESTIONS or not available_questions:
            closing_msg = "Thank you for your time. Your answers were insightful. Have a great day!"
            audio_b64 = await asyncio.to_thread(synthesize_speech, closing_msg)
            await asyncio.to_thread(interviews_collection.update_one, {"sessionId": session_id}, {"$set": {"status": "completed"}})
            await websocket.send_json({"type": "interview_complete", "text": closing_msg, "audio_base64": audio_b64})
            return

        next_q_id = evaluation.get("next_question_id", "follow_up")
        if next_q_id == "follow_up":
            actual_id = f"dyn_followup_{len(current_asked_ids)}"
            ideal_rubric = []
        else:
            actual_id = next_q_id
            orig = next((q for q in pool if q.get("id") == next_q_id), None)
            ideal_rubric = orig.get("ideal_answer_rubric", []) if orig else []

        current_question = {
            "id": actual_id,
            "question_text": evaluation.get("next_question_text"),
            "ideal_answer_rubric": ideal_rubric
        }

        await asyncio.to_thread(
            interviews_collection.update_one,
            {"sessionId": session_id},
            {"$push": {"asked_question_ids": actual_id, "transcript": {"speaker": "interviewer", "text": current_question["question_text"]}}}
        )

        audio_b64 = await asyncio.to_thread(synthesize_speech, current_question["question_text"])
        await websocket.send_json({
            "type": "ai_question",
            "text": current_question["question_text"],
            "audio_base64": audio_b64
        })

    # Boot up the very first question if starting fresh
    if not asked_ids:
        await asyncio.to_thread(
            interviews_collection.update_one, 
            {"sessionId": session_id}, 
            {
                "$push": {
                    "asked_question_ids": current_question["id"],
                    # WE MUST ADD THE FIRST QUESTION TO THE TRANSCRIPT LOG!
                    "transcript": {
                        "speaker": "interviewer",
                        "text": current_question["question_text"],
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            }
        )
        audio_b64 = await asyncio.to_thread(synthesize_speech, current_question["question_text"])
        await websocket.send_json({"type": "ai_question", "text": current_question["question_text"], "audio_base64": audio_b64})
        
    try:
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "start_recording":
                if processor: processor.stop_and_submit() 
                processor = StreamingAudioProcessor(session_id, loop, on_interim, process_final_answer)
                processor.start()
                
            elif data["type"] == "audio_chunk":
                if processor:
                    chunk = base64.b64decode(data["audio"])
                    processor.add_audio(chunk)
                
            elif data["type"] == "stop_recording":
                if processor:
                    processor.stop_and_submit()
                    processor = None
                
    except WebSocketDisconnect:
        if processor: processor.stop_and_submit()
        if session_id in active_connections:
            del active_connections[session_id]

# ==========================================
# 4. TEST UI ROUTE (HTML FRONTEND)
# ==========================================
@app.get("/test-interview/{session_id}")
async def get_test_ui(session_id: str):
    try:
        file_path = os.path.join(os.path.dirname(__file__), "index.html") 
        with open(file_path, "r", encoding="utf-8") as file:
            html_content = file.read()
        html_content = html_content.replace("SESSION_ID_PLACEHOLDER", session_id)
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="index.html file not found.")
