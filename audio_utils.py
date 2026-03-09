import os
import base64
from google.cloud import texttospeech
from google.api_core.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

# Initialize Google Cloud TTS Client using API Key
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        client_options = ClientOptions(api_key=api_key)
        tts_client = texttospeech.TextToSpeechClient(client_options=client_options)
        print("[TTS] Google Cloud TTS Authenticated via API Key.")
    else:
        print("Warning: GOOGLE_API_KEY not found in .env file.")
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
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-IN",
            name="en-IN-Chirp3-HD-Erinome" # Your preferred voice
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
        print(f"[TTS ERROR] {e}")
        return ""