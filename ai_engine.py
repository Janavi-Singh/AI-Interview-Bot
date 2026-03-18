import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure the NEW Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "gemini-2.5-flash-lite"

def get_gemini_json_response(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> dict:
    """Helper function to call Gemini using the NEW SDK and force a strict JSON response."""
    
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        response_mime_type="application/json",
    )
    
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=config
    )
    
    return json.loads(response.text)


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
        print(f"[GEMINI] Parsing Job Description {contest_id}...")
        parsed_data = get_gemini_json_response(system_prompt, jd_text,temperature=0.2)
        parsed_data["contest_id"] = contest_id
        return parsed_data
    except Exception as e:
        print(f"[GEMINI ERROR] JD Parsing failed: {e}")
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
        print(f"[GEMINI] Parsing Resume {js_id}...")
        parsed_data = get_gemini_json_response(system_prompt, resume_text,temperature=0.2)
        parsed_data["js_id"] = js_id
        return parsed_data
    except Exception as e:
        print(f"[GEMINI ERROR] Resume Parsing failed: {e}")
        raise Exception(f"Resume Parsing failed: {str(e)}")


def generate_question_pool(parsed_jd: dict, parsed_resume: dict) -> list:
    """Generates exactly 15 questions upfront for zero-latency live selection."""
    candidate_name = parsed_resume.get("candidate_profile", {}).get("name", "the candidate")

    system_prompt = f"""
    You are 'Tara', a Senior Technical Interviewer AI at Hiringhood. 
    Your task is to generate a massive pool of EXACTLY 15 personalized interview questions based on the JD and Resume. 

    REQUIREMENTS:
    1. Technical (4 questions): Core hard skills from the JD.
    2. Experience validation (5 questions): Deep dives into their specific past projects and work experience.
    3. Scenario-based (3 questions): Hypothetical situations.
    4. Behavioral (3 questions): Culture fit and soft skills.

    RULES:
    - The first question (id: "q1") MUST be a welcoming greeting asking {candidate_name} to introduce themselves.
    - DO NOT ask generic questions. Tie them specifically to the candidate's resume and mention their projects or experience names and make it personalised.
    - Write the 'question_text' exactly how you would say it out loud.
    - Ask only one short question per ID in around 25-35 words. Do NOT combine multiple questions into one. Each question must be standalone and focused on a single topic or skill.

    You MUST output a valid JSON object matching this EXACT schema:
    {{
        "question_pool": [
            {{
                "id": "string (e.g., 'q1', 'q2'... up to 'q15')",
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
    
    Generate exactly 15 highly personalized questions now.
    """

    try:
        print(f"[GEMINI] Generating 15-Question Pool for {candidate_name}...")
        parsed_data = get_gemini_json_response(system_prompt, user_prompt, temperature=0.7)
        questions = parsed_data.get("question_pool", [])
        print(f"[GEMINI] Successfully generated {len(questions)} questions.")
        return questions
        
    except Exception as e:
        print(f"[GEMINI ERROR] Question Generation failed: {e}")
        raise Exception(f"Question Generation failed: {str(e)}")


def evaluate_candidate_answer(current_question: dict, user_answer: str, available_questions: list, recent_context: str = "") -> dict:
    """Evaluates the answer and selects the next question ID from the 15-question buffer."""
    print("[GEMINI EVAL] Evaluating answer and dynamically routing...")
    
    try:
        pool_summary = [
            {"id": q.get("id", "unknown"), "topic": q.get("topic", "general")} 
            for q in available_questions
        ]
        
        rubric = current_question.get("ideal_answer_rubric", [])
        rubric_text = ", ".join(rubric) if isinstance(rubric, list) else str(rubric)

        system_prompt = """
        You are 'Tara', an AI Technical Interviewer. Score the candidate's answer and maintain a natural conversation.
        
        1. Score the 'Candidate Answer' out of 10 based on the 'Ideal Answer Rubric'.
        2. Decide the next step:
           - If the answer was poor, set 'next_question_id' to "follow_up" and write a 'next_question_text' to dig deeper.
           - If the answer was satisfactory, select a 'next_question_id' from the 'Available Next Questions' pool. CRITICAL: Choose a question that covers a DIFFERENT topic or a DIFFERENT project. You must explore all areas of their profile and not get stuck on one single subject.
        3. Ask the next question in a natural, engaging way. Use a smooth conversational transition (e.g., "Great explanation. Shifting gears to a different topic...").
        4. Do not mention the candidate's name. Use their project or experience names naturally.
        5. Ask exactly ONE short question in around 25-35 words. Do NOT compound questions or list options. 
        
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
        
        --- AVAILABLE NEXT QUESTIONS TOPICS (Pick one if moving on to a new topic) ---
        {json.dumps(pool_summary, indent=2)}
        """

        evaluation = get_gemini_json_response(system_prompt, user_prompt, temperature=0.2)
        print(f"[GEMINI EVAL] Success! Score: {evaluation.get('score')}")
        
        valid_ids = [q.get("id") for q in available_questions]
        if evaluation.get("next_question_id") not in valid_ids and evaluation.get("next_question_id") != "follow_up":
            evaluation["next_question_id"] = valid_ids[0] if valid_ids else "follow_up"
            
        return evaluation

    except Exception as e:
        print(f"[GEMINI ERROR] Critical Evaluation Failure: {e}")
        return {
            "score": 0, 
            "feedback": f"Evaluation failed safely: {str(e)}", 
            "next_question_text": "Thank you. Let's move on to our next topic.",
            "next_question_id": available_questions[0].get("id") if available_questions else "follow_up"
        }
        
        
def generate_interview_report(jd_context: dict, candidate_profile: dict, qa_pairs: list, avg_score: float) -> dict:
    """
    Generates the AI Analysis portion of the interview report using Gemini.
    """
    print("[GEMINI REPORT] Generating detailed AI analysis...")
    
    try:
        qa_summary = ""
        for idx, qa in enumerate(qa_pairs, 1):
            qa_summary += f"\n[Q{idx}] [{qa.get('origin', 'Pre-planned')}] Interviewer: {qa['question']}\n"
            qa_summary += f"[A{idx}] Candidate: {qa['answer']}\n"
            qa_summary += f"AI Score: {qa['score']}/10\n"

        system_prompt = f"""
        You are an elite Senior Technical Hiring Manager conducting a post-interview debrief.
        Your task is to analyze the candidate's interview transcript and generate a brutal, honest, and highly detailed JSON report.

        EVALUATION DIRECTIVES:
        1. Detect Dodging: If the candidate gives vague answers, says "I don't remember", or refuses to answer, heavily penalize their 'depth_of_knowledge' and note it in 'areas_for_improvement'. Take note of when the interviewer had to use a "[Dynamic Follow-up]" to get a real answer.
        2. Fact-Check Resume: Compare their answers against what they claimed on their resume. Note any discrepancies in 'resume_alignment'.
        3. Be Specific: Do not use generic phrases. Quote specific moments or technologies from the transcript in your strengths and weaknesses.

        OUTPUT FORMAT (STRICT JSON):
        You MUST output a valid JSON object matching this EXACT schema:
        {{
            "overall_evaluation": "A 3-4 sentence professional summary of their performance. Mention if they dodged questions or lacked depth.",
            "recommendation": "Choose exactly ONE: 'Strong Hire', 'Hire', 'Maybe', or 'No Hire'. Tie this to their average score of {avg_score}/10.",
            "key_strengths": [
                "Specific strength with evidence from the transcript",
                "Another specific strength"
            ],
            "areas_for_improvement": [
                "Specific weakness, gap, or evasive behavior noted in the transcript",
                "Another specific technical gap"
            ],
            "technical_assessment": {{
                "depth_of_knowledge": number (1-10),
                "problem_solving": number (1-10),
                "communication": number (1-10),
                "experience_relevance": number (1-10)
            }},
            "resume_alignment": "1-2 sentences explaining if their interview answers backed up their resume claims.",
            "job_fit": "1-2 sentences on their alignment with the specific role requirements.",
            "next_steps": "Actionable next step (e.g., 'Consider additional screening', 'Proceed to final round', 'Reject')."
        }}
        """

        user_prompt = f"""
        --- JOB DESCRIPTION ---
        {json.dumps(jd_context, indent=2)}
        
        --- CANDIDATE PROFILE ---
        {json.dumps(candidate_profile, indent=2)}
        
        --- INTERVIEW TRANSCRIPT & SCORES ---
        Average Q&A Score: {avg_score}/10
        {qa_summary}
        """

        print(f"[GEMINI REPORT] Requesting detailed analysis ({len(user_prompt)} chars)...")
        ai_analysis_data = get_gemini_json_response(system_prompt, user_prompt, temperature=0.2)
        print("[GEMINI REPORT] Successfully generated dynamic analysis.")
        return ai_analysis_data

    except Exception as e:
        print(f"[GEMINI REPORT ERROR] Parsing failed: {e}")
        return {
            "overall_evaluation": "The interview was completed, but the AI evaluation engine encountered an error generating the detailed summary.",
            "recommendation": "Review Manually",
            "key_strengths": ["Completed the interview session"],
            "areas_for_improvement": ["Manual review required"],
            "technical_assessment": {"depth_of_knowledge": int(avg_score), "problem_solving": int(avg_score), "communication": int(avg_score), "experience_relevance": int(avg_score)},
            "resume_alignment": "Manual review required.",
            "job_fit": "Manual review required.",
            "next_steps": "Review raw transcript manually."
        }
