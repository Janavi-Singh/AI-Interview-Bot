import os
import queue
import threading
import asyncio
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.api_core.client_options import ClientOptions 
from dotenv import load_dotenv

load_dotenv()

# Initialize Client
try:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.getenv("GOOGLE_CLOUD_PROJECT"):
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        
        # FIXED 1: We MUST explicitly route the client connection to a region that hosts Chirp
        client_options = ClientOptions(api_endpoint="us-central1-speech.googleapis.com")
        stt_client = SpeechClient(client_options=client_options)
        
        # FIXED 2: We MUST set the recognizer's physical location to match the client endpoint
        recognizer_path = f"projects/{project_id}/locations/us-central1/recognizers/_"
        
        print("[STT] Google Cloud STT V2 (Chirp) Initialized in us-central1.")
    else:
        print("[STT INIT ERROR] Missing GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CLOUD_PROJECT in .env")
        stt_client = None
except Exception as e:
    print(f"[STT INIT ERROR] {e}")
    stt_client = None


class StreamingAudioProcessor:
    def __init__(self, session_id, loop, on_interim_callback, on_final_callback):
        self.session_id = session_id
        self.loop = loop
        self.on_interim_callback = on_interim_callback
        self.on_final_callback = on_final_callback
        
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.stream_thread = None
        self.final_transcript = ""
        
        self.recognition_config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=["en-US"],
            model="chirp", 
            features=cloud_speech.RecognitionFeatures(
                enable_automatic_punctuation=True
            )
        )
        
        self.streaming_config = cloud_speech.StreamingRecognitionConfig(
            config=self.recognition_config,
            streaming_features=cloud_speech.StreamingRecognitionFeatures(
                interim_results=True
            )
        )

    def start(self):
        """Starts a fresh Google STT Stream for the current answer."""
        if self.is_running: return
        self.is_running = True
        self.final_transcript = ""
        self.stream_thread = threading.Thread(target=self._stream_audio, daemon=True)
        self.stream_thread.start()
        print(f"[STT] New V2 Chirp audio stream started for {self.session_id}")

    def add_audio(self, audio_bytes):
        if self.is_running:
            self.audio_queue.put(audio_bytes)

    def stop_and_submit(self):
        """Closes the stream and triggers the final evaluation."""
        if not self.is_running: return
        print(f"[STT] Stream closed for {self.session_id}. Finalizing transcript...")
        self.is_running = False
        self.audio_queue.put(None) 

    def _audio_generator(self):
        yield cloud_speech.StreamingRecognizeRequest(
            recognizer=recognizer_path,
            streaming_config=self.streaming_config
        )
        
        while True:
            chunk = self.audio_queue.get()
            if chunk is None:
                break
            yield cloud_speech.StreamingRecognizeRequest(audio=chunk)

    def _stream_audio(self):
        if not stt_client:
            print("[STT ERROR] Client not initialized. Check your JSON credentials.")
            return

        try:
            requests = self._audio_generator()
            responses = stt_client.streaming_recognize(requests=requests)
            
            for response in responses:
                if not response.results: continue
                result = response.results[0]
                if not result.alternatives: continue
                
                transcript = result.alternatives[0].transcript
                
                if result.is_final:
                    self.final_transcript += transcript.strip() + " "
                    asyncio.run_coroutine_threadsafe(self.on_interim_callback(self.final_transcript), self.loop)
                else:
                    display_text = self.final_transcript + transcript
                    asyncio.run_coroutine_threadsafe(self.on_interim_callback(display_text), self.loop)

        except Exception as e:
            print(f"[STT STREAM FINISHED/INTERRUPTED] {e}")

        finally:
            final_text = self.final_transcript.strip()
            asyncio.run_coroutine_threadsafe(self.on_final_callback(final_text), self.loop)
