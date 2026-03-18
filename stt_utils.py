import os
import queue
import threading
import asyncio
from google.cloud import speech
from google.api_core.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

# Initialize Client
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    client_options = ClientOptions(api_key=api_key) if api_key else None
    stt_client = speech.SpeechClient(client_options=client_options) if api_key else None
    print("[STT] Google Cloud STT Initialized.")
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
        
        # Native WebM Opus Configuration matches frontend MediaRecorder perfectly
        self.config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000, 
            language_code="en-US",
            alternative_language_codes=["en-IN","en-GB","en-AU"],
            enable_automatic_punctuation=True,
            model="latest_long"
        )
        self.streaming_config = speech.StreamingRecognitionConfig(
            config=self.config,
            interim_results=True,
        )

    def start(self):
        """Starts a fresh Google STT Stream for the current answer."""
        if self.is_running: return
        self.is_running = True
        self.final_transcript = ""
        self.stream_thread = threading.Thread(target=self._stream_audio, daemon=True)
        self.stream_thread.start()
        print(f"[STT] New audio stream started for {self.session_id}")

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
        while True:
            chunk = self.audio_queue.get()
            if chunk is None:
                break
            yield chunk

    def _stream_audio(self):
        if not stt_client:
            print("[STT ERROR] Client not initialized.")
            return

        try:
            audio_generator = self._audio_generator()
            
            # Just yield the raw audio chunks
            requests = (speech.StreamingRecognizeRequest(audio_content=content) for content in audio_generator)
            
            # FIXED: Pass config as an explicit argument, exactly as the library requires!
            responses = stt_client.streaming_recognize(
                config=self.streaming_config,
                requests=requests
            )
            
            for response in responses:
                if not response.results: continue
                result = response.results[0]
                if not result.alternatives: continue
                
                transcript = result.alternatives[0].transcript
                
                if result.is_final:
                    # Lock in the final sentence of this chunk
                    self.final_transcript += transcript.strip() + " "
                    asyncio.run_coroutine_threadsafe(self.on_interim_callback(self.final_transcript), self.loop)
                else:
                    # Show the locked-in text plus the current guess
                    display_text = self.final_transcript + transcript
                    asyncio.run_coroutine_threadsafe(self.on_interim_callback(display_text), self.loop)

        except Exception as e:
            print(f"[STT STREAM FINISHED/INTERRUPTED] {e}")

        finally:
            # Trigger the final Mistral evaluation when the stream is completely closed
            final_text = self.final_transcript.strip()
            asyncio.run_coroutine_threadsafe(self.on_final_callback(final_text), self.loop)
