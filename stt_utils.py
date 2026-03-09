import os
import time
import queue
import threading
import asyncio
from google.cloud import speech  # Using STT V1
from google.api_core.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

# Initialize STT V1 Client globally using ONLY the API Key
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        client_options = ClientOptions(api_key=api_key)
        stt_client = speech.SpeechClient(client_options=client_options)
        print("[STT] Google Cloud STT V1 (Streaming) Initialized via API Key.")
    else:
        print("Warning: GOOGLE_API_KEY not found in .env file.")
        stt_client = None
except Exception as e:
    print(f"Warning: Google Cloud STT not initialized. {e}")
    stt_client = None

class StreamingAudioProcessor:
    def __init__(self, session_id, loop, on_interim_callback, on_final_callback):
        self.session_id = session_id
        self.loop = loop
        self.on_interim_callback = on_interim_callback
        self.on_final_callback = on_final_callback
        
        self.audio_queue = queue.Queue(maxsize=100)
        self.is_running = False
        self.is_listening = False
        self.stream_thread = None
        
        self.current_transcript = ""
        self.last_final_time = None
        self.SILENCE_THRESHOLD = 2.5
        self.restart_lock = threading.Lock()
        self.restart_count = 0
        self.max_restarts = 300
        self.last_audio_time = time.time()
        self.force_new_stream = False 

        self.rate = 16000
        
        # STT V1 Configuration
        self.config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.rate,
            language_code="en-IN", # Matches your TTS accent
            enable_automatic_punctuation=True,
            model="latest_long",   # Explicitly requesting the better V1 model
            use_enhanced=True      # Allows the use of premium models
        )
        
        self.streaming_config = speech.StreamingRecognitionConfig(
            config=self.config,
            interim_results=True,
        )

    def reset_stream_connection(self):
        with self.restart_lock:
            if self.is_running and not self.force_new_stream:
                self.force_new_stream = True
                print(f"[STT RESET] Proactive stream reset triggered for {self.session_id}")

    def start(self):
        with self.restart_lock:
            if self.is_running: return
            self.is_running = True
            self.is_listening = True
            self.restart_count = 0
            self.force_new_stream = False
            self.stream_thread = threading.Thread(target=self._stream_audio, daemon=True)
            self.stream_thread.start()
            print(f"[STT] Started for {self.session_id}")

    def stop(self):
        with self.restart_lock:
            if not self.is_running: return
            self.is_running = False
            self.is_listening = False
            self.force_new_stream = False
            while not self.audio_queue.empty():
                try: self.audio_queue.get_nowait()
                except queue.Empty: break
            self.audio_queue.put(None)
            print(f"[STT] Stopped for {self.session_id}")

    def mute(self):
        self.is_listening = False
        self.current_transcript = ""
        self.last_final_time = None
        while not self.audio_queue.empty():
            try: self.audio_queue.get_nowait()
            except queue.Empty: break

    def unmute(self):
        self.is_listening = True
        self.current_transcript = ""
        self.last_final_time = None

    def add_audio(self, audio_bytes):
        if self.is_running and self.is_listening:
            try:
                self.audio_queue.put(audio_bytes, block=False)
                self.last_audio_time = time.time()
            except queue.Full:
                pass

    def _audio_generator(self):
        silent_chunk = b'\x00' * int(self.rate / 10)
        self.last_audio_time = time.time()
        
        while self.is_running:
            if self.force_new_stream:
                with self.restart_lock:
                    self.force_new_stream = False
                return 
            
            try:
                chunk = self.audio_queue.get(timeout=1)
                if chunk is None: break
                self.last_audio_time = time.time()
                yield chunk
            except queue.Empty:
                if not self.is_listening:
                    yield silent_chunk
                elif time.time() - self.last_audio_time > 8:
                    yield silent_chunk
                    self.last_audio_time = time.time()
                else:
                    continue

    def _create_streaming_requests(self, audio_generator):
        # V1 allows sending config and audio in the same format
        yield speech.StreamingRecognizeRequest(streaming_config=self.streaming_config)
        for content in audio_generator:
            yield speech.StreamingRecognizeRequest(audio_content=content)

    def _stream_audio(self):
        if not stt_client:
            print("[STT ERROR] Cannot stream, client not initialized.")
            return

        while self.is_running and self.restart_count < self.max_restarts:
            try:
                audio_generator = self._audio_generator()
                request_iterator = self._create_streaming_requests(audio_generator)
                
                responses = stt_client.streaming_recognize(requests=request_iterator)
                self._process_responses(responses)
                
                time.sleep(0.1)
            except Exception as e:
                if "Exception iterating requests" in str(e) or "Out of range" in str(e):
                    if self.is_listening and self.is_running:
                        time.sleep(0.5)
                        continue
                    break
                if self._restart_stream():
                    time.sleep(0.5)
                    continue
                break

    def _restart_stream(self):
        with self.restart_lock:
            if not self.is_running or self.restart_count >= self.max_restarts: return False
            self.restart_count += 1
            while not self.audio_queue.empty():
                try: self.audio_queue.get_nowait()
                except queue.Empty: break
            return True

    def _process_responses(self, responses):
        for response in responses:
            if not self.is_running: break
            if not response.results: continue
            
            result = response.results[0]
            if not result.alternatives: continue
            
            transcript = result.alternatives[0].transcript
            
            if not result.is_final:
                if self.is_listening:
                    # Combine locked-in sentences with current guess
                    display_text = self.current_transcript + transcript
                    asyncio.run_coroutine_threadsafe(self.on_interim_callback(display_text), self.loop)
            else:
                if transcript.strip() and len(transcript.strip()) > 1 and self.is_listening:
                    # Lock in the final sentence
                    self.current_transcript += transcript.strip() + " "
                    self.last_final_time = time.time()
                    
                    # Update UI to show the new locked-in text
                    asyncio.run_coroutine_threadsafe(self.on_interim_callback(self.current_transcript), self.loop)
                    
                    # Check for 2.5 seconds of silence to submit the answer
                    threading.Thread(target=self._check_silence, daemon=True).start()

    def _check_silence(self):
        time.sleep(self.SILENCE_THRESHOLD)
        if self.last_final_time and (time.time() - self.last_final_time) >= self.SILENCE_THRESHOLD:
            if self.current_transcript.strip() and self.is_listening:
                complete_text = self.current_transcript.strip()
                self.current_transcript = ""
                self.last_final_time = None
                
                if len(complete_text) > 2:
                    asyncio.run_coroutine_threadsafe(self.on_final_callback(complete_text), self.loop)
            else:
                self.current_transcript = ""
                self.last_final_time = None