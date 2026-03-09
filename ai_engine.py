import os
import json
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()
mistral_client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

def parse_jd(jd_text: str, contest_id: str) -> dict:
    system_prompt = """
    You are an expert Technical Recruiter AI. Extract the job details from the provided Job Description.
    You MUST output a valid JSON object matching this EXACT schema:
    {
      "jobOverview": "string",
      "keyResponsibilities": ["string"],
      "job_requirements": {
        "job_title_or_role": "string",
        "employment": "string",
        "years_experience_minimum": "number (extract only the number)",
        "years_experience_maximum": "number (extract only the number)",
        "num_positions": "string",
        "ctc_in_inr_minimum": "number (extract only the number)",
        "ctc_in_inr_maximum": "number (extract only the number)",
        "education": "string",
        "officeHours": "string",
        "work_location": "string (city only)",
        "mode_of_work": "string",
        "interview_rounds": "string",
        "salaries_paid_on": "string (last_day_of_month or First of every month or other)",
        "must_have": ["string"],
        "good_to_have": ["string"]
      },
      "employer_details": {
        "Company_name": "string",
        "Company_website": "string",
        "Company_type": "string (prod or service)"
      }
    }
    """
    
    try:
        print(f"[MISTRAL] Parsing Job Description {contest_id}...")
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": jd_text}
            ],
            response_format={"type": "json_object"} 
        )
        parsed_data = json.loads(response.choices[0].message.content)
        parsed_data["contest_id"] = contest_id
        return parsed_data
    except Exception as e:
        print(f"[MISTRAL ERROR] JD Parsing failed: {e}")
        raise Exception(f"JD Parsing failed: {str(e)}")

def parse_resume(resume_text: str, js_id: str) -> dict:
    system_prompt = """
    You are an expert Technical Recruiter AI. Extract the candidate's details from the provided Resume.
    You MUST output a valid JSON object matching this EXACT schema:
    {
        "candidate_profile": {
            "name": "string",
            "email": "string",
            "skills": ["string"],
            "experience": ["string (Summarize each role)"],
            "projects": [
                {
                    "title": "string",
                    "description": "string",
                    "technologies": ["string"]
                }
            ]
        }
    }
    """
    try:
        print(f"[MISTRAL] Parsing Resume {js_id}...")
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": resume_text}
            ],
            response_format={"type": "json_object"} 
        )
        parsed_data = json.loads(response.choices[0].message.content)
        parsed_data["js_id"] = js_id
        return parsed_data
    except Exception as e:
        print(f"[MISTRAL ERROR] Resume Parsing failed: {e}")
        raise Exception(f"Resume Parsing failed: {str(e)}")


def generate_question_pool(parsed_jd: dict, parsed_resume: dict) -> list:
    """Generates exactly 20 questions upfront for zero-latency live selection."""
    candidate_name = parsed_resume.get("candidate_profile", {}).get("name", "the candidate")

    system_prompt = f"""
    You are 'Tara', a Senior Technical Interviewer AI at Hiringhood. 
    Your task is to generate a massive pool of EXACTLY 20 personalized interview questions based on the JD and Resume. 

    REQUIREMENTS (Generate EXACTLY 5 questions for each category):
    1. Technical (6 questions): Core hard skills from the JD.
    2. Experience validation (7 questions): Deep dives into their specific past projects.
    3. Scenario-based (4 questions): Hypothetical situations.
    4. Behavioral (3 questions): Culture fit and soft skills.


    RULES:
    - The first question (id: "intro_001") MUST be a welcoming greeting asking {candidate_name} to introduce themselves.
    - DO NOT ask generic questions. Tie them specifically to the candidate's resume and mention their projects or experience names and make it personalised. (e.g., "I see you used React in your InterviewSimplify project...")
    - Write the 'question_text' exactly how you would say it out loud.

    You MUST output a valid JSON object matching this EXACT schema:
    {{
        "question_pool": [
            {{
                "id": "string (e.g., 'q1', 'q2'... up to 'q20')",
                "category": "technical | scenario | behavioral | experience_validation",
                "difficulty": "beginner | intermediate | advanced",
                "topic": "string (e.g., 'API Design')",
                "question_text": "string (The core question)",
                "ideal_answer_rubric": ["keyword1", "keyword2", "concept3"] 
            }}
        ]
    }}
    """
    
    user_prompt = f"""
    --- JOB DESCRIPTION ---
    {json.dumps(parsed_jd, indent=2)}
    
    --- CANDIDATE PROFILE ---
    {json.dumps(parsed_resume, indent=2)}
    
    Generate exactly 20 highly personalized questions now.
    """

    try:
        print(f"[MISTRAL] Generating 20-Question Pool for {candidate_name}...")
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"} 
        )

        parsed_data = json.loads(response.choices[0].message.content)
        questions = parsed_data.get("question_pool", [])
        print(f"[MISTRAL] Successfully generated {len(questions)} questions.")
        return questions
        
    except Exception as e:
        print(f"[MISTRAL ERROR] Question Generation failed: {e}")
        raise Exception(f"Question Generation failed: {str(e)}")


def evaluate_candidate_answer(current_question: dict, user_answer: str, available_questions: list, recent_context: str = "") -> dict:
    """Evaluates the answer and selects the next question ID from the 20-question buffer."""
    print("[MISTRAL EVAL] Evaluating answer and dynamically routing...")
    
    try:
        pool_summary = [
            {"id": q.get("id", "unknown"), "topic": q.get("topic", "general")} 
            for q in available_questions
        ]
        
        rubric = current_question.get("ideal_answer_rubric", [])
        rubric_text = ", ".join(rubric) if isinstance(rubric, list) else str(rubric)

        system_prompt = """
        You are 'Tara', an AI Technical Interviewer. Score the candidate's {candidate_name} answer and maintain a natural conversation.
        
        1. Score the 'Candidate Answer' out of 10 based on the 'Ideal Answer Rubric'.
        2. Decide the next step:
           - If the answer was poor or lacked detail, set 'next_question_id' to "follow_up". Write a 'next_question_text' that digs deeper into what they just said.
           - If the answer was good, select the BEST 'next_question_id' from the 'Available Next Questions' pool. Then, write 'next_question_text' by combining a smooth conversational transition with the topic of that chosen question.
        3. Ask the next question in a natural, engaging way. Do NOT just say "Next question: {question_text}". Instead, weave it into the conversation (e.g., "Great insight on X! Now, let's talk about Y..."). And also mention the candidate's name and thier related projects or experiences to make it more personalized.
        You MUST output a valid JSON object matching this EXACT schema:
        {
            "score": number,
            "feedback": "string (private notes for the recruiter)",
            "next_question_text": "string (The actual, smooth, conversational text you will say next)",
            "next_question_id": "string (The ID from Available Next Questions, OR 'follow_up')"
        }
        """

        user_prompt = f"""
        --- RECENT CONVERSATION CONTEXT ---
        {recent_context}

        --- CURRENT TURN ---
        Question Asked: {current_question.get('question_text', '')}
        Ideal Answer Rubric: {rubric_text}
        
        Candidate Answer: "{user_answer}"
        
        --- AVAILABLE NEXT QUESTIONS TOPICS (Pick one if moving on) ---
        {json.dumps(pool_summary, indent=2)}
        """

        print("[MISTRAL EVAL] Sending request to Mistral API...")
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"} 
        )

        evaluation = json.loads(response.choices[0].message.content)
        print(f"[MISTRAL EVAL] Success! Score: {evaluation.get('score')}")
        
        valid_ids = [q.get("id") for q in available_questions]
        if evaluation.get("next_question_id") not in valid_ids and evaluation.get("next_question_id") != "follow_up":
            evaluation["next_question_id"] = valid_ids[0] if valid_ids else "follow_up"
            
        return evaluation

    except Exception as e:
        print(f"[MISTRAL ERROR] Critical Evaluation Failure: {e}")
        return {
            "score": 5, 
            "feedback": f"Evaluation failed safely: {str(e)}", 
            "next_question_text": "Thank you. Let's move on to our next topic.",
            "next_question_id": available_questions[0].get("id") if available_questions else "follow_up"
        }