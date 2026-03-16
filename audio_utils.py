import os
import base64
from google.cloud import texttospeech
from dotenv import load_dotenv

load_dotenv()

try:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    # Authenticate securely using the same Service Account JSON as the STT Engine
    if project_id and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        tts_client = texttospeech.TextToSpeechClient()
        print("[TTS] Google Cloud TTS Initialized securely via Service Account.")
    else:
        print("Warning: GOOGLE_CLOUD_PROJECT or GOOGLE_APPLICATION_CREDENTIALS missing.")
        tts_client = None
except Exception as e:
    print(f"Warning: Google Cloud TTS not initialized. {e}")
    tts_client = None

def synthesize_speech(text: str) -> str:
    """Converts text to speech and returns a base64 encoded audio string."""
    if not tts_client or not text:
        return ""
        
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Uses standard Neural2 voice to ensure compatibility
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-IN",
            name="en-IN-Neural2-A" 
        )
        
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=1.0
        )
        
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        return base64.b64encode(response.audio_content).decode("utf-8")
    except Exception as e:
        print(f"\n[🚨 TTS ERROR] {e}\n")
        return ""
