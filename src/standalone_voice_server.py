# FILE: src/standalone_voice_server.py
import os
import sys
import time
import json
import socket
import threading
import logging
import uuid
import base64
import io
import wave
import tempfile
import numpy as np
from pathlib import Path

# --- Add this right after imports ---
CODE_VERSION = "2025-04-12_2210_Refactor" # Use a unique identifier/timestamp
# --- End Add ---

# --- Logging Setup ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s' # Added thread name
log_file = Path(__file__).parent.parent / 'articulate3d_server.log' # Log file in project root

# Configure root logger for console output
logging.basicConfig(level=logging.DEBUG, format=log_format, handlers=[logging.StreamHandler(sys.stdout)])

# Create a specific logger for this module
logger = logging.getLogger(__name__) # Use __name__ for logger name
logger.setLevel(logging.DEBUG) # Ensure this logger captures DEBUG

# Add file handler
try:
    # Ensure the log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, mode='a') # Use append mode
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.setLevel(logging.DEBUG) # Log DEBUG to file too
    # Prevent duplicate logging to root/console if handlers are added here
    if not logger.hasHandlers():
         logger.addHandler(file_handler)
         logger.propagate = False # Prevent propagation if we added our own handler
    else: # If handlers already exist (e.g., basicConfig added one), just add file handler
         logger.addHandler(file_handler)

    logger.info(f"--- Log session started. Logging to {log_file} ---")
except Exception as e:
    logging.error(f"Failed to set up file logging to {log_file}: {e}", exc_info=True)

# --- Add this after logger is configured ---
logger.critical(f"--- SERVER SCRIPT RUNNING - VERSION: {CODE_VERSION} ---")
# --- End Add ---


# --- Environment Variable Loading ---
try:
    # Ensure dotenv is imported if available
    import dotenv
    project_root = Path(__file__).parent.parent
    env_path = project_root / '.env'
    if env_path.exists():
        logger.info(f"Loading environment variables from {env_path}")
        dotenv.load_dotenv(dotenv_path=env_path, override=True) # Override ensures .env takes precedence
    else:
        logger.info(".env file not found, relying on system environment variables.")

    # Verify API Key loaded
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.critical("GEMINI_API_KEY not found or not set in environment/.env file. Server cannot function.")
        # Optionally sys.exit(1) here if you want it to hard stop
    else:
         logger.info("GEMINI_API_KEY loaded successfully.")
         # Attempt global configuration ONCE at startup - library might require this
         try:
             import google.generativeai as genai # Import here for configure call
             genai.configure(api_key=GEMINI_API_KEY)
             logger.info("Global genai configuration attempted.")
         except ImportError:
             logger.error("Failed to import google.generativeai for global configure call.")
         except Exception as e:
             logger.error(f"Failed to perform global genai.configure: {e}", exc_info=True)

except ImportError:
    logger.warning("python-dotenv module not found. Will rely solely on system environment variables.")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Still try to get it
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.critical("GEMINI_API_KEY not found or not set in system environment. Server cannot function.")
    # Also attempt global configure here if dotenv wasn't found
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
             import google.generativeai as genai # Import here for configure call
             genai.configure(api_key=GEMINI_API_KEY)
             logger.info("Global genai configuration attempted (no dotenv).")
        except ImportError:
             logger.error("Failed to import google.generativeai for global configure call (no dotenv).")
        except Exception as e:
             logger.error(f"Failed to perform global genai.configure (no dotenv): {e}", exc_info=True)


# --- Library Imports & Dependency Check ---
# Place imports after env vars are loaded, as some libraries might use them during import
DEPENDENCIES_INSTALLED = True
try:
    import google.generativeai as genai
    logger.debug("Successfully imported google.generativeai")
except ImportError as e:
    logger.critical(f"Failed to import google.generativeai: {e}. Please run setup.py.")
    DEPENDENCIES_INSTALLED = False

try:
    import whisper
    logger.debug("Successfully imported whisper")
except ImportError as e:
    logger.critical(f"Failed to import whisper: {e}. Please run setup.py.")
    DEPENDENCIES_INSTALLED = False

try:
    from google.cloud import speech
    logger.debug("Successfully imported google.cloud.speech")
except ImportError as e:
    logger.warning(f"Failed to import google.cloud.speech: {e}. Google Cloud STT method unavailable.")

try:
    import speech_recognition as sr
    logger.debug("Successfully imported speech_recognition")
except ImportError as e:
    logger.critical(f"Failed to import speech_recognition: {e}. Please run setup.py.")
    DEPENDENCIES_INSTALLED = False

try:
    import pyaudio
    logger.debug("Successfully imported pyaudio")
except ImportError as e:
    logger.warning(f"Failed to import pyaudio: {e}. Microphone input might fail.")
    DEPENDENCIES_INSTALLED = False # PyAudio is critical for mic input

try:
    import vosk
    logger.debug("Successfully imported vosk")
except ImportError as e:
    logger.critical(f"Failed to import vosk: {e}. Please install vosk (`pip install vosk`).")
    DEPENDENCIES_INSTALLED = False

# Import collections (standard library, should always work)
try:
    import collections
    logger.debug("Successfully imported collections.")
except ImportError as e:
    # This is highly unlikely but handle it just in case
    logger.error(f"CRITICAL FAILURE: Failed to import standard library 'collections': {e}", exc_info=True)
    # We could potentially exit here, but let's log critically and see if anything else works
    # DEPENDENCIES_INSTALLED = False # Mark as failed if collections is critical later
    pass # Allow to continue for now


# Exit if core dependencies are missing
if not DEPENDENCIES_INSTALLED:
     logger.critical("Core dependencies missing. Exiting server.")
     sys.exit(1)


# --- Server Configuration ---
HOST = '127.0.0.1'
PORT = 65432
stop_server = threading.Event()
pending_context_requests = {} # request_id -> {data}
client_configs = {} # conn -> {model_name, method} - NO model instance stored
execution_errors = {} # request_id -> {"error_type": ..., "error_message": ..., "conn": conn} # Store conn for cleanup
client_chat_sessions = {} # conn -> Gemini ChatSession object # Added for future chat implementation

# --- Wake Word & VAD Configuration ---
VOSK_MODEL_PATH = str(Path(__file__).parent.parent / "models" / "vosk-model-small-en-us-0.15") # ADJUST PATH AS NEEDED
WAKE_WORDS = ["okay blender","okay listen"] # Add more if needed
WAKE_WORD_JSON = json.dumps(WAKE_WORDS + ["[unk]"]) # For Vosk recognizer
WAKE_WORD_JSON = json.dumps(WAKE_WORDS + ["[unk]"]) # For Vosk recognizer

# --- SpeechRecognition Configuration ---
SR_ENERGY_THRESHOLD = 300 # Default, might need tuning
SR_PAUSE_THRESHOLD = 0.8 # Seconds of silence before phrase is considered complete
SR_PHRASE_TIME_LIMIT = 15 # Max seconds for a command phrase

# --- Helper Functions ---

def format_blender_context(context_data):
    """Formats the rich context data into a readable string for the AI prompt."""
    if not context_data:
        return "No Blender context provided."

    parts = []
    parts.append(f"Scene: {context_data.get('scene_name', 'N/A')}")
    parts.append(f"Mode: {context_data.get('mode', 'UNKNOWN')}")

    active_obj = context_data.get('active_object')
    if active_obj:
        active_str = f"Active Object: {active_obj.get('name', 'N/A')} (Type: {active_obj.get('type', 'N/A')}, " \
                     f"Loc: {active_obj.get('location')}, Rot: {active_obj.get('rotation_euler')}, Scale: {active_obj.get('scale')})"
        parts.append(active_str)
    else:
        parts.append("Active Object: None")

    selected_objs = context_data.get('selected_objects', [])
    if selected_objs:
        selected_strs = [f"{sel.get('name', 'N/A')} ({sel.get('type', 'N/A')})" for sel in selected_objs]
        parts.append(f"Selected Objects: [{', '.join(selected_strs)}]")
    else:
        parts.append("Selected Objects: []")

    scene_objs = context_data.get('scene_objects', [])
    if scene_objs:
        parts.append(f"Other Scene Objects: [{', '.join(scene_objs)}]")
    else:
         parts.append("Other Scene Objects: []")


    return "\n".join(parts)

# --- AI Processing Functions (Refactored for Chat) ---
DEFAULT_GENERATION_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.8,
    "top_k": 40,
    "max_output_tokens": 16192,
}
DEFAULT_SAFETY_SETTINGS = [
    {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
    {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
    {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
    {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
]

def process_text_with_chat(chat_session, text_command: str, blender_context: dict = None):
    """Processes text using the provided chat session."""
    if not chat_session:
        logger.error("[Chat Text] No chat session provided.")
        return None

    context_info = format_blender_context(blender_context)
    # Construct the message to send, including current context
    # The chat history is managed by the chat_session object itself
    prompt = f"""
**Command:** {text_command}
**Current Blender Context:**
{context_info}

**Instructions:**
1.  **Output Python Code Only:** Your response must contain ONLY the Python script. Do not include ```python, explanations, comments, introductions, or any other text.
2.  **Use Blender 4.x API:** Ensure the script uses `bpy` commands compatible with Blender 4.x.
3.  **Prioritize `bpy.data`:** Whenever possible, use the `bpy.data` API for creating/manipulating objects, meshes, materials, etc. It is more robust than `bpy.ops` when run from scripts. Only use `bpy.ops` if `bpy.data` is not suitable for the specific task.
4.  **Consider History:** Remember previous commands and responses in this chat session to understand context like "it", "that object", etc.
5.  **Handle Errors:** If the command is unclear, too complex, or requires `bpy.ops` in an unsafe way, output ONLY the comment: `# Error: Command cannot be processed.`
"""
    # Add retry prompt logic if needed (can be integrated here or in the calling function)
    if "**Previous Script Failed Execution in Blender:**" in text_command or \
       "**Previous Generation Attempt Failed:**" in text_command:
        prompt = text_command # Use the full retry prompt passed in
        logger.debug("[Chat Text] Using provided text as full retry prompt for chat.")


    try:
        logger.debug(f"[Chat Text] Sending message to chat session...")
        # Send the combined prompt/context to the existing chat session
        response = chat_session.send_message(
            prompt,
            generation_config=DEFAULT_GENERATION_CONFIG,
            safety_settings=DEFAULT_SAFETY_SETTINGS
        )
        logger.debug(f"[Chat Text] Chat response received.")

        script = ""
        # Accessing response text might differ slightly for chat sessions
        if hasattr(response, 'parts') and response.parts:
            if hasattr(response.parts[0], 'text'):
                 script = response.parts[0].text.strip()
            else:
                 logger.warning("[Chat Text] Response part exists but has no 'text' attribute.")
        elif hasattr(response, 'text'):
             script = response.text.strip()
        else:
            logger.warning("[Chat Text] Chat response has no 'parts' or 'text'. Checking feedback.")
            if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason'):
                block_reason = response.prompt_feedback.block_reason
                safety_ratings = response.prompt_feedback.safety_ratings
                logger.warning(f"[Chat Text] Request blocked: {block_reason}. Ratings: {safety_ratings}")
                script = f"# Error: Content blocked by API ({block_reason})"
            else:
                logger.warning(f"[Chat Text] Unknown response structure: {response}")
                script = "# Error: Could not parse chat response."

        # Stricter validation
        if not script or not script.strip() or "# Error:" in script:
             logger.warning(f"[Chat Text] Chat returned an invalid/error script: '{script}'")
             return None

        logger.info("[Chat Text] Received valid script from chat session.")
        return script

    except Exception as e:
        logger.error(f"[Chat Text] Error during chat session send_message: {type(e).__name__} - {e}", exc_info=True)
        return None


def process_audio_with_chat(chat_session, audio_bytes: bytes, blender_context: dict = None, mime_type: str = "audio/wav") -> str | None:
    """Processes audio using the provided chat session (for initial audio command)."""
    # Note: Retries for audio commands will likely fall back to process_text_with_chat
    #       using the transcribed text and error context.
    if not chat_session:
        logger.error("[Chat Audio] No chat session provided.")
        return None

    logger.debug(f"[Chat Audio] Processing audio command with chat session.")

    context_info = format_blender_context(blender_context)
    # Construct the prompt part of the message
    prompt = f"""
Listen to the following audio command and translate it into a `bpy` Python script compatible with Blender 4.x.

**Instructions:**
1. **Output Python Code Only:** Your response must contain ONLY the Python script. Do not include ```python, explanations, comments, introductions, or any other text.
2. **Use Blender 4.x API:** The script must exclusively use `bpy` commands compatible with Blender 4.x. Avoid any deprecated or removed enums, properties, or functions.
3. **Render Engine Enums:** Always use Blender 4.x valid values. For example:
    - Use `'BLENDER_EEVEE_NEXT'` instead of `'BLENDER_EEVEE'`.
    - Use `'CYCLES'`, `'HYDRA_STORM'`, or `'BLENDER_WORKBENCH'` where applicable.
4. **Prioritize `bpy.data`:** Whenever possible, use the `bpy.data` API for creating and manipulating objects, meshes, and materials. Reserve `bpy.ops` only for actions that cannot be done through `bpy.data`.
5. **Consider Context and History:** Remember prior commands and responses in this chat session to ensure coherent and context-aware scripting.
make sure the script is valid and can be executed in blender.
another importatant note: if asked for models like model of a plane , a three by three rubix cube, a flower vase , a car etc make sure to group the items like for a three by three rubix cube, group the items in a collection called rubix cube(here all the cubes) or all the parts of a flower vase in a collection called flower vase.
6. **Handle Errors:** If the command is ambiguousd`# Error: Command cannot be processed with reason in one word.`

**Current Blender Context:**
{context_info}

**Script:**

"""

    try:
        # Prepare the audio part
        audio_part = None
        if hasattr(genai, 'types') and hasattr(genai.types, 'Part'):
            audio_part = genai.types.Part.from_data(data=audio_bytes, mime_type=mime_type)
        else:
            audio_part = {"mime_type": mime_type, "data": base64.b64encode(audio_bytes).decode('utf-8')}

        if not audio_part:
             logger.error("[Chat Audio] Failed to create audio part for Gemini.")
             return None

        # Combine prompt and audio data for the message
        contents_list = [prompt, audio_part]

        logger.debug(f"[Chat Audio] Sending message (prompt + audio) to chat session...")
        response = chat_session.send_message(
            contents_list,
            generation_config=DEFAULT_GENERATION_CONFIG,
            safety_settings=DEFAULT_SAFETY_SETTINGS
        )
        logger.debug(f"[Chat Audio] Chat response received.")

        script = ""
        # Accessing response text (same logic as text processing)
        if hasattr(response, 'parts') and response.parts:
            if hasattr(response.parts[0], 'text'):
                 script = response.parts[0].text.strip()
            else:
                 logger.warning("[Chat Audio] Response part exists but has no 'text' attribute.")
        elif hasattr(response, 'text'):
             script = response.text.strip()
        else:
            logger.warning("[Chat Audio] Chat response has no 'parts' or 'text'. Checking feedback.")
            if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason'):
                block_reason = response.prompt_feedback.block_reason
                safety_ratings = response.prompt_feedback.safety_ratings
                logger.warning(f"[Chat Audio] Request blocked: {block_reason}. Ratings: {safety_ratings}")
                script = f"# Error: Content blocked by API ({block_reason})"
            else:
                logger.warning(f"[Chat Audio] Unknown response structure: {response}")
                script = "# Error: Could not parse chat response."

        # Stricter validation
        if not script or not script.strip() or "# Error:" in script:
             logger.warning(f"[Chat Audio] Chat returned an invalid/error script: '{script}'")
             return None

        logger.info("[Chat Audio] Received valid script from chat session.")
        return script

    except Exception as e:
        logger.error(f"[Chat Audio] Error during chat session send_message for audio: {type(e).__name__} - {e}", exc_info=True)
        return None


# --- Transcription Functions ---
# (Keep transcribe_with_whisper and transcribe_with_google_stt as they are)
whisper_model_cache = {}

def transcribe_with_whisper(audio_bytes: bytes) -> str | None:
    """Transcribe audio using OpenAI Whisper (small model)."""
    global whisper_model_cache
    if 'whisper' not in sys.modules:
        logger.error("[Whisper] Whisper library not available.")
        return None

    model_name = "small"
    try:
        if model_name not in whisper_model_cache:
            logger.info(f"[Whisper] Loading Whisper model: {model_name}...")
            whisper_model_cache[model_name] = whisper.load_model(model_name)
            logger.info(f"[Whisper] Model '{model_name}' loaded.")

        model = whisper_model_cache[model_name]
        if not model:
             logger.error(f"[Whisper] Model object for '{model_name}' is invalid after loading attempt.")
             return None

        tmp_file_path = None
        try:
            addon_dir = Path(__file__).parent.parent
            temp_audio_dir = addon_dir / "temp_audio"
            temp_audio_dir.mkdir(exist_ok=True)

            with tempfile.NamedTemporaryFile(dir=temp_audio_dir, suffix=".wav", delete=False) as tmp_file:
                tmp_file_path = tmp_file.name
                tmp_file.write(audio_bytes)

            logger.debug(f"[Whisper] Transcribing temporary file: {tmp_file_path}")
            result = model.transcribe(tmp_file_path, fp16=False)
            text = result.get("text", "").strip()
            logger.info(f"[Whisper] Transcription result: '{text}'")
            return text

        except Exception as e:
            logger.error(f"[Whisper] Error during transcription processing: {e}", exc_info=True)
            if isinstance(e, RuntimeError) and "ffmpeg" in str(e).lower():
                 logger.error("[Whisper] This might be an ffmpeg issue. Ensure ffmpeg is installed and in PATH.")
            return None
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                try: os.remove(tmp_file_path)
                except OSError as e_del: logger.error(f"[Whisper] Error deleting temp file {tmp_file_path}: {e_del}")

    except Exception as e:
        logger.error(f"[Whisper] Error setting up Whisper transcription (model loading?): {e}", exc_info=True)
        return None


def transcribe_with_google_stt(audio_bytes: bytes, sample_rate: int = 16000) -> str | None:
    """Transcribe audio using Google Cloud Speech-to-Text."""
    if 'google.cloud.speech' not in sys.modules:
         logger.warning("[Google STT] Google Cloud Speech library not available.")
         return None

    try:
        logger.info("[Google STT] Transcribing with Google Cloud STT...")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        client = None
        if not credentials_path:
             logger.warning("[Google STT] GOOGLE_APPLICATION_CREDENTIALS not set. Attempting default authentication.")
             client = speech.SpeechClient()
        else:
             if Path(credentials_path).is_file():
                 logger.debug(f"[Google STT] Using credentials from: {credentials_path}")
                 client = speech.SpeechClient.from_service_account_file(credentials_path)
             else:
                 logger.error(f"[Google STT] Credentials file not found at: {credentials_path}")
                 return None

        if not client: # Should not happen if above logic is correct, but check anyway
            logger.error("[Google STT] Failed to initialize SpeechClient.")
            return None

        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code="en-US",
        )

        response = client.recognize(config=config, audio=audio)

        if not response.results or not response.results[0].alternatives:
            logger.warning("[Google STT] Received no transcription results.")
            return None

        transcript = response.results[0].alternatives[0].transcript.strip()
        logger.info(f"[Google STT] Transcription result: '{transcript}'")
        return transcript

    except Exception as e:
        logger.error(f"[Google STT] Error during Google Cloud STT transcription: {e}", exc_info=True)
        return None

# --- Server Threads ---

def server_audio_listener_thread(conn: socket.socket, addr):
    """Handles wake word detection (Vosk) and command capture (SpeechRecognition)."""
    logger.info(f"[{addr}] Audio listener thread started (Vosk/SpeechRecognition).")
    # Ensure necessary libraries are loaded
    if 'vosk' not in sys.modules or 'pyaudio' not in sys.modules or 'speech_recognition' not in sys.modules:
        logger.error(f"[{addr}] Missing vosk, pyaudio, or speech_recognition. Listener thread stopping.")
        return

    # --- Vosk Initialization ---
    vosk_model = None
    try:
        if not Path(VOSK_MODEL_PATH).exists():
            logger.error(f"[{addr}] Vosk model not found at: {VOSK_MODEL_PATH}")
            raise FileNotFoundError("Vosk model path invalid")
        vosk_model = vosk.Model(VOSK_MODEL_PATH)
        logger.info(f"[{addr}] Vosk model loaded successfully from {VOSK_MODEL_PATH}")
    except Exception as e:
        logger.error(f"[{addr}] Failed to load Vosk model: {e}", exc_info=True)
        try: conn.sendall(json.dumps({"status": "error", "message": f"Failed to load Vosk model: {e}"}).encode())
        except: pass
        return # Cannot proceed without model

    # --- SpeechRecognition Initialisation ---
    sr_recognizer = sr.Recognizer()
    sr_recognizer.energy_threshold = SR_ENERGY_THRESHOLD
    sr_recognizer.pause_threshold = SR_PAUSE_THRESHOLD
    # We'll open the Microphone source only when needed

    # --- PyAudio Initialization (for Vosk wake word listening) ---
    pa_vosk = None
    stream_vosk = None
    SAMPLE_RATE = 16000 # Vosk and SR typically use 16000 Hz
    CHANNELS = 1
    FORMAT = pyaudio.paInt16 # 16-bit PCM
    # Chunk size for Vosk processing
    VOSK_CHUNK_DURATION_MS = 100 # Process in 100ms chunks for wake word
    VOSK_CHUNK_SIZE = int(SAMPLE_RATE * VOSK_CHUNK_DURATION_MS / 1000)
    BYTES_PER_SAMPLE = pyaudio.get_sample_size(FORMAT)

    try:
        pa_vosk = pyaudio.PyAudio()
        stream_vosk = pa_vosk.open(format=FORMAT,
                         channels=CHANNELS,
                         rate=SAMPLE_RATE,
                         input=True,
                         frames_per_buffer=VOSK_CHUNK_SIZE)
        logger.info(f"[{addr}] PyAudio stream opened for Vosk (Rate: {SAMPLE_RATE}, Chunk: {VOSK_CHUNK_SIZE} frames / {VOSK_CHUNK_DURATION_MS}ms)")

        # --- Vosk Recognizer Initialization ---
        vosk_recognizer = vosk.KaldiRecognizer(vosk_model, SAMPLE_RATE, WAKE_WORD_JSON) # Pass grammar here
        logger.info(f"[{addr}] Vosk recognizer initialized for wake words: {WAKE_WORDS}")

    except Exception as e:
        logger.error(f"[{addr}] Failed to initialize PyAudio stream or Vosk Recognizer: {e}", exc_info=True)
        if stream_vosk: stream_vosk.close()
        if pa_vosk: pa_vosk.terminate()
        try: conn.sendall(json.dumps({"status": "error", "message": f"Audio/Vosk init error: {e}"}).encode())
        except: pass
        return

    # --- State Variables ---
    STATE_IDLE = 0 # Listening for wake word via Vosk/PyAudio
    STATE_LISTENING_COMMAND = 1 # Capturing command via SpeechRecognition
    STATE_PROCESSING_COMMAND = 2 # Command captured, being processed
    current_state = STATE_IDLE

    try:
        # Send initial status
        if is_socket_connected(conn):
            try: conn.sendall(json.dumps({"status": "info", "message": "Listening for wake word..."}).encode())
            except socket.error as send_err:
                 logger.warning(f"[{addr}] Failed to send initial 'listening' status: {send_err}")
                 if not is_socket_connected(conn): return # Exit if send fails and disconnected
        else:
            logger.warning(f"[{addr}] Socket closed before sending initial 'listening' status. Aborting listener.")
            return

        # --- Main Audio Loop ---
        while not stop_server.is_set() and is_socket_connected(conn):
            try:
                # Only read from Vosk stream if in IDLE state
                if current_state == STATE_IDLE:
                    chunk_data = stream_vosk.read(VOSK_CHUNK_SIZE, exception_on_overflow=False)
                else:
                    # Avoid reading from Vosk stream while listening/processing command
                    time.sleep(0.1) # Small sleep to prevent busy-waiting
                    continue
            except IOError as e:
                 if hasattr(e, 'errno') and e.errno == pyaudio.paInputOverflowed:
                      logger.warning(f"[{addr}] PyAudio input overflowed. Skipping chunk.")
                      continue
                 else:
                      logger.error(f"[{addr}] PyAudio stream read error: {e}", exc_info=True)
                      break # Exit loop on other read errors

            if not chunk_data:
                logger.warning(f"[{addr}] Empty chunk read from audio stream.")
                time.sleep(0.01)
                continue

            # --- State Machine Logic ---

            # STATE: IDLE (Listening for Wake Word via Vosk)
            if current_state == STATE_IDLE:
                if vosk_recognizer.AcceptWaveform(chunk_data):
                    result = json.loads(vosk_recognizer.Result())
                    detected_text = result.get('text', '')
                    # Check if any wake word is present (simple substring check)
                    if any(word in detected_text for word in WAKE_WORDS):
                        logger.info(f"[{addr}] Wake word detected by Vosk: '{detected_text}'")
                        vosk_recognizer.Reset() # Reset Vosk state

                        # --- Switch to SpeechRecognition for command capture ---
                        current_state = STATE_LISTENING_COMMAND
                        logger.info(f"[{addr}] Transitioning to LISTENING_COMMAND state.")
                        try: conn.sendall(json.dumps({"status": "info", "message": "Wake word detected, listening for command..."}).encode())
                        except: pass

                        # Stop Vosk stream temporarily
                        if stream_vosk:
                            try:
                                stream_vosk.stop_stream()
                                logger.debug(f"[{addr}] Stopped Vosk PyAudio stream.")
                            except Exception as e_stop: logger.warning(f"[{addr}] Error stopping Vosk stream: {e_stop}")

                        # Capture command using SpeechRecognition
                        command_audio_bytes = None
                        try:
                            with sr.Microphone(sample_rate=SAMPLE_RATE) as source:
                                logger.info(f"[{addr}] Adjusting for ambient noise (1s)...")
                                try: conn.sendall(json.dumps({"status": "info", "message": "Adjusting noise..."}).encode())
                                except: pass
                                sr_recognizer.adjust_for_ambient_noise(source, duration=1)
                                logger.info(f"[{addr}] Listening for command via SpeechRecognition...")
                                try: conn.sendall(json.dumps({"status": "info", "message": "Listening..."}).encode())
                                except: pass
                                audio_command = sr_recognizer.listen(source, phrase_time_limit=SR_PHRASE_TIME_LIMIT)
                                command_audio_bytes = audio_command.get_wav_data()
                                logger.info(f"[{addr}] Command captured by SpeechRecognition ({len(command_audio_bytes)} bytes).")
                        except sr.WaitTimeoutError:
                            logger.warning(f"[{addr}] No command heard after wake word (timeout).")
                        except Exception as sr_err:
                            logger.error(f"[{addr}] Error during SpeechRecognition listen: {sr_err}", exc_info=True)
                            try: conn.sendall(json.dumps({"status": "error", "message": f"Error capturing command: {sr_err}"}).encode())
                            except: pass

                        # --- Process captured command (if any) ---
                        if command_audio_bytes:
                            current_state = STATE_PROCESSING_COMMAND
                            logger.debug(f"[{addr}] Transitioning to PROCESSING state.")
                            # Process in this thread for simplicity (consider threading later if needed)
                            process_captured_command(conn, addr, command_audio_bytes, SAMPLE_RATE, FORMAT, CHANNELS)
                        else:
                            # No command captured, go back to idle
                            current_state = STATE_IDLE
                            logger.debug(f"[{addr}] No command captured, returning to IDLE state.")
                            try: conn.sendall(json.dumps({"status": "info", "message": "Listening for wake word..."}).encode())
                            except: pass

                        # --- Restart Vosk stream ---
                        if stream_vosk and not stream_vosk.is_active():
                             try:
                                 stream_vosk.start_stream()
                                 logger.debug(f"[{addr}] Restarted Vosk PyAudio stream.")
                             except Exception as e_start:
                                 logger.error(f"[{addr}] Failed to restart Vosk stream: {e_start}", exc_info=True)
                                 # Handle error - maybe try closing and reopening?
                                 break # Exit loop if stream can't restart

                        # If processing happened, reset state after processing call returns
                        if current_state == STATE_PROCESSING_COMMAND:
                            current_state = STATE_IDLE
                            logger.debug(f"[{addr}] Reset state to IDLE after processing.")
                            try: conn.sendall(json.dumps({"status": "info", "message": "Listening for wake word..."}).encode())
                            except: pass

                # else: # Optional: Check partial result for faster feedback
                #     partial_result = json.loads(vosk_recognizer.PartialResult())
                #     if any(word in partial_result.get('partial', '') for word in WAKE_WORDS):
                #          logger.debug(f"[{addr}] Wake word potentially in partial: {partial_result.get('partial')}")
                #          # Don't trigger yet, wait for final result for robustness

            # STATE: LISTENING_COMMAND / PROCESSING_COMMAND (Handled within IDLE state block now)
            # These states are now transient within the wake word detection logic
            elif current_state in [STATE_LISTENING_COMMAND, STATE_PROCESSING_COMMAND]:
                 # We should ideally not be reading from Vosk stream here
                 # This case handles the transition back to IDLE after processing/timeout
                 logger.debug(f"[{addr}] In state {current_state}, waiting for transition back to IDLE.")
                 time.sleep(0.1) # Prevent busy loop if something goes wrong
                 pass # Loop continues, state should reset soon

            # Check connection status periodically
            # if not is_socket_connected(conn): break # Already checked at loop start

        # End of main while loop

    except KeyboardInterrupt:
        logger.info(f"[{addr}] Keyboard interrupt received in listener thread.")
    except Exception as e:
        logger.error(f"[{addr}] Unhandled error in audio listener main loop: {type(e).__name__} - {e}", exc_info=True)
    finally:
        logger.info(f"[{addr}] Cleaning up audio listener resources...")
        if stream_vosk:
            try: stream_vosk.stop_stream()
            except Exception as e_stop: logger.warning(f"[{addr}] Error stopping Vosk stream: {e_stop}")
            try: stream_vosk.close()
            except Exception as e_close: logger.warning(f"[{addr}] Error closing Vosk stream: {e_close}")
            logger.debug(f"[{addr}] Vosk PyAudio stream closed.")
        if pa_vosk:
            try: pa_vosk.terminate()
            except Exception as e_term: logger.warning(f"[{addr}] Error terminating PyAudio for Vosk: {e_term}")
            logger.debug(f"[{addr}] Vosk PyAudio instance terminated.")
        # Note: SpeechRecognition manages its own PyAudio instance internally via sr.Microphone context manager
        logger.info(f"[{addr}] Audio listener thread finished.")


# --- Helper function to process the captured command audio ---
def process_captured_command(conn: socket.socket, addr: str, audio_data: bytes, sample_rate: int, audio_format, channels: int):
    """Processes the audio captured after the wake word."""
    logger.info(f"[{addr}] Processing captured command audio ({len(audio_data)} bytes)...")

    if not audio_data:
        logger.warning(f"[{addr}] No audio data provided for processing.")
        return

    if not is_socket_connected(conn):
        logger.warning(f"[{addr}] Client disconnected before command processing.")
        return

    try:
        config = client_configs.get(conn) # Use .get for safety
        if not config:
            logger.warning(f"[{addr}] Configuration missing for connection during command processing. Skipping.")
            try: conn.sendall(json.dumps({"status": "error", "message": "Client configuration missing."}).encode())
            except: pass
            return

        current_method = config.get('method', 'whisper')
        current_model = config.get('model_name', 'gemini-1.5-flash') # Ensure a default model
        logger.info(f"[{addr}] Processing command using method: {current_method}, Model: {current_model}")

        # Convert raw PCM to WAV format in memory for compatibility
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(pyaudio.get_sample_size(audio_format))
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        audio_bytes_wav = wav_buffer.getvalue()
        logger.debug(f"[{addr}] Converted captured PCM to WAV format ({len(audio_bytes_wav)} bytes).")


        # --- Add audio saving (optional, but useful for debugging) ---
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"command_audio_{timestamp}_{unique_id}.wav"
            save_dir = Path(__file__).parent.parent / "temp_audio"
            save_dir.mkdir(exist_ok=True) # Ensure dir exists
            save_path = save_dir / filename
            with open(save_path, 'wb') as wf_save:
                wf_save.write(audio_bytes_wav)
            logger.info(f"[{addr}] Saved captured command audio to: {save_path}")
        except Exception as save_err:
            logger.error(f"[{addr}] Failed to save captured command audio: {save_err}", exc_info=True)
        # --- End audio saving ---

        request_id = str(uuid.uuid4())
        text_result = None
        audio_to_process = None
        message_to_client = "Processing command..."

        if current_method == "gemini":
            # Gemini needs WAV usually, ensure mime type is correct
            audio_to_process = audio_bytes_wav
            message_to_client = "Processing audio command with Gemini..."
        elif current_method == "whisper":
            text_result = transcribe_with_whisper(audio_bytes_wav) # Pass WAV data
            message_to_client = f"Transcribed command (Whisper): {text_result}" if text_result else "Whisper transcription failed."
        elif current_method == "google_stt":
            text_result = transcribe_with_google_stt(audio_bytes_wav, sample_rate=sample_rate) # Pass WAV data
            message_to_client = f"Transcribed command (Google STT): {text_result}" if text_result else "Google STT transcription failed."
        else:
            logger.error(f"[{addr}] Unknown audio method configured: {current_method}")
            try: conn.sendall(json.dumps({"status": "error", "message": f"Unknown audio method: {current_method}"}).encode())
            except: pass
            return # Exit processing function

        # Store pending request only if transcription/selection was successful (or if using direct audio)
        if text_result is not None or audio_to_process is not None:
             pending_context_requests[request_id] = {
                 'audio_bytes': audio_to_process, # This is WAV data if method=gemini
                 'text': text_result,
                 'model_name': current_model,
                 'method': current_method,
                 'conn': conn,
                 'addr': addr
             }
             logger.debug(f"[{addr}] Stored pending request {request_id} (Method: {current_method}) for captured command.")

             try:
                 conn.sendall(json.dumps({
                     "status": "request_context",
                     "request_id": request_id,
                     "message": message_to_client
                 }).encode())
                 logger.debug(f"[{addr}] Sent context request {request_id} to client for captured command.")
             except socket.error as send_err:
                 logger.error(f"[{addr}] Failed to send context request {request_id}: {send_err}")
                 if request_id in pending_context_requests:
                     del pending_context_requests[request_id]
        else:
             logger.warning(f"[{addr}] No text or audio obtained for method {current_method} for captured command. Cannot proceed.")
             try: conn.sendall(json.dumps({"status": "error", "message": f"Failed to get input via {current_method} for command."}).encode())
             except: pass

    except Exception as e:
        logger.error(f"[{addr}] Error in process_captured_command: {type(e).__name__} - {e}", exc_info=True)
        try: conn.sendall(json.dumps({"status": "error", "message": f"Error processing command audio: {e}"}).encode())
        except: pass


# --- Original SpeechRecognition based listener (KEEP FOR REFERENCE OR FALLBACK?) ---
# def server_audio_listener_thread_speechrecognition(conn: socket.socket, addr):
#     """Handles audio capture using SpeechRecognition and sends for processing."""
#     logger.info(f"[{addr}] Audio listener thread started (SpeechRecognition).")
#     # ... (original code from before) ...
#     finally:
#         logger.info(f"[{addr}] Audio listener thread (SpeechRecognition) finished.")


# --- Client Message Handling ---
def client_message_handler_thread(conn: socket.socket, addr):
    """Handles messages received from a specific client connection."""
    logger.info(f"[{addr}] Message handler thread started (Version: {CODE_VERSION}).")

    try: conn.sendall(json.dumps({"status": "ready", "message": "Server ready and connected."}).encode())
    except socket.error as send_err:
        logger.warning(f"[{addr}] Failed to send initial ready message: {send_err}")

    # Rely on recv/send errors to detect disconnection within the loop
    while not stop_server.is_set():
        # logger.debug(f"[{addr}] Handler loop iteration start.") # Removed noisy log
        try:
            # logger.debug(f"[{addr}] Setting socket timeout and attempting recv...") # Removed noisy log
            conn.settimeout(0.5)
            client_data = conn.recv(8192)
            if not client_data:
                logger.info(f"[{addr}] Client disconnected (recv returned empty).")
                # --- Start Cleanup ---
                logger.info(f"[{addr}] Performing cleanup for handler thread due to empty recv.")
                if conn in client_configs:
                    try: del client_configs[conn]
                    except KeyError: pass
                    logger.debug(f"[{addr}] Removed client config during cleanup.")
                # Also clear chat session for this client
                if conn in client_chat_sessions:
                    try: del client_chat_sessions[conn]
                    except KeyError: pass
                    logger.debug(f"[{addr}] Removed client chat session during cleanup.")

                requests_to_remove = [req_id for req_id, data in pending_context_requests.items() if data.get('conn') == conn]
                for req_id in requests_to_remove:
                    try: del pending_context_requests[req_id]
                    except KeyError: pass
                if requests_to_remove: logger.debug(f"[{addr}] Removed {len(requests_to_remove)} pending context requests during cleanup.")

                close_socket(conn, addr)
                # --- End Cleanup ---
                break
            logger.debug(f"[{addr}] Received {len(client_data)} bytes from client.")

            try:
                client_message = json.loads(client_data.decode('utf-8'))
                logger.debug(f"[{addr}] Received message: {client_message}")
                msg_type = client_message.get("type")

                if msg_type == "configure":
                    logger.info(f"[{addr}] Processing 'configure' message (Version: {CODE_VERSION}).")
                    model_name = client_message.get("model")
                    method = client_message.get("method")
                    if model_name and method:
                        # Store config first
                        client_configs[conn] = {"model_name": model_name, "method": method}
                        logger.info(f"[{addr}] Client configured: Model={model_name}, Method={method}")

                        # --- Initialize or Reset Chat Session ---
                        try:
                            logger.info(f"[{addr}] Initializing/Resetting chat session for model: {model_name}")
                            model = genai.GenerativeModel(model_name)
                            # Start a fresh chat session each time configuration happens
                            chat = model.start_chat(history=[])
                            client_chat_sessions[conn] = chat # Store the session object
                            logger.info(f"[{addr}] Chat session initialized/reset successfully.")
                        except Exception as chat_init_err:
                            logger.error(f"[{addr}] Failed to initialize chat session: {chat_init_err}", exc_info=True)
                            # Clear any potentially old session if init fails
                            if conn in client_chat_sessions: del client_chat_sessions[conn]
                            # Inform client? For now, just log error. Addon might fail later.
                            pass

                        # --- Send Confirmation ---
                        try:
                            conn.sendall(json.dumps({"status": "info", "message": f"Configuration received (Model: {model_name}, Method: {method})"}).encode())
                            logger.debug(f"[{addr}] Successfully sent config confirmation.")
                        except socket.error as send_err:
                            logger.warning(f"[{addr}] Failed to send config confirmation: {send_err}")
                            break # Exit loop if sending confirmation fails
                        logger.debug(f"[{addr}] Finished processing 'configure' message block.")
                    else:
                        logger.warning(f"[{addr}] Invalid configuration message received: {client_message}")
                        try: conn.sendall(json.dumps({"status":"error", "message":"Invalid config message received."}).encode())
                        except: pass

                elif msg_type == "execution_error":
                    # --- Handle Execution Error Report from Client ---
                    request_id = client_message.get("request_id")
                    error_type = client_message.get("error_type", "UnknownType")
                    error_message = client_message.get("error_message", "Unknown error message.")
                    if request_id:
                        # Store the error, associated with the request ID
                        execution_errors[request_id] = {"error_type": error_type, "error_message": error_message, "conn": conn} # Store conn for cleanup
                        logger.warning(f"[{addr}] Received execution error report for request {request_id}: {error_type} - {error_message}")
                        # The retry logic within context_response will now pick this up if needed.
                    else:
                        logger.error(f"[{addr}] Received execution_error message without a request_id: {client_message}")
                    # --- End Error Handling ---

                elif msg_type == "context_response":
                    request_id = client_message.get("request_id")
                    received_context = client_message.get("context")
                    logger.debug(f"[{addr}] Received context response for request: {request_id}")

                    if request_id in pending_context_requests:
                        pending_data = pending_context_requests.pop(request_id)

                        if pending_data.get('conn') != conn:
                             logger.warning(f"[{addr}] Mismatched connection for context response {request_id}. Ignoring.")
                             continue

                        script = None
                        method = pending_data['method']
                        model_name = pending_data['model_name']
                        original_text = pending_data.get('text') # For whisper/google_stt
                        audio_bytes = pending_data.get('audio_bytes') # For gemini direct audio
                        max_retries = 2 # Attempt 1 + 1 retry

                        # --- Get Chat Session ---
                        chat_session = client_chat_sessions.get(conn)
                        if not chat_session:
                             logger.error(f"[{addr}] No chat session found for connection during context response {request_id}. Cannot proceed.")
                             # Send error back to client?
                             try:
                                 conn.sendall(json.dumps({"status":"error", "message":"Chat session missing on server.", "request_id": request_id, "original_text": original_text}).encode())
                             except: pass
                             continue # Skip processing this request

                        for attempt in range(max_retries):
                            logger.info(f"[{addr}] Script generation attempt {attempt + 1}/{max_retries} for request {request_id} (Method: {method})")
                            prompt_for_gemini = ""
                            is_retry = False

                            # Check if there was a reported execution error for this request ID
                            reported_error = execution_errors.pop(request_id, None) # Get error and remove it

                            if reported_error:
                                # --- Construct Retry Prompt with Execution Error ---
                                is_retry = True
                                logger.info(f"[{addr}] Retrying request {request_id} due to reported execution error.")
                                error_type = reported_error['error_type']
                                error_msg = reported_error['error_message']
                                original_command_text = original_text if original_text else "(Audio Command)"

                                prompt_for_gemini = f"""
**Previous Script Failed Execution in Blender:**
The script generated for the command '{original_command_text}' failed with the following error:
```
{error_type}: {error_msg}
```
**Please analyze the original command and the execution error, then generate a corrected Blender 4.x Python script.**

**Instructions:**
1.  **Fix the Error:** Address the specific `{error_type}` reported.
2.  **Output Python Code Only:** Your response must contain ONLY the Python script. Do not include ```python, explanations, comments, introductions, or any other text.
3.  **Use Blender 4.x API:** Ensure the script uses `bpy` commands compatible with Blender 4.x.
4.  **Prioritize `bpy.data`:** Whenever possible, use the `bpy.data` API for creating/manipulating objects, meshes, materials, etc. It is more robust than `bpy.ops` when run from scripts. Only use `bpy.ops` if `bpy.data` is not suitable for the specific task.

**Original Command:** {original_command_text}
**Current Blender Context:**
{format_blender_context(received_context)}

**Corrected Script:**
"""
                                # --- End Retry Prompt Construction ---
                            elif attempt > 0:
                                # --- Construct Retry Prompt for Generation Failure ---
                                is_retry = True
                                logger.info(f"[{addr}] Retrying request {request_id} due to initial generation failure.")
                                original_command_text = original_text if original_text else "(Audio Command)"
                                prompt_for_gemini = f"""
**Previous Generation Attempt Failed:**
The previous attempt to generate a script for the command '{original_command_text}' failed (returned no script or an error comment).

**Please analyze the original command and try again to generate a valid Blender 4.x Python script.**

**Instructions:**
1.  **Output Python Code Only:** Your response must contain ONLY the Python script. Do not include ```python, explanations, comments, introductions, or any other text.
2.  **Use Blender 4.x API:** Ensure the script uses `bpy` commands compatible with Blender 4.x.
3.  **Prioritize `bpy.data`:** Whenever possible, use the `bpy.data` API for creating/manipulating objects, meshes, materials, etc. It is more robust than `bpy.ops` when run from scripts. Only use `bpy.ops` if `bpy.data` is not suitable for the specific task.

**Original Command:** {original_command_text}
**Current Blender Context:**
{format_blender_context(received_context)}

**Script:**
"""
                                # --- End Generation Failure Retry Prompt ---

                            # --- Call appropriate Gemini function using CHAT SESSION ---
                            if method == "gemini" and not is_retry: # First attempt with direct audio
                                if audio_bytes:
                                    script = process_audio_with_chat(chat_session, audio_bytes, received_context) # Use chat function
                                else:
                                    logger.error(f"[{addr}] No audio data in pending request {request_id} for Gemini method on attempt {attempt + 1}.")
                                    script = None # Ensure script is None if no audio
                                    break # No point retrying if audio is missing
                            elif method in ["whisper", "google_stt"] or is_retry: # Use text prompt for transcription methods or any retry
                                text_input_for_gemini = prompt_for_gemini if is_retry else original_text
                                if text_input_for_gemini:
                                    # Pass the full prompt if retrying, otherwise just the original text
                                    script = process_text_with_chat(chat_session, text_input_for_gemini, received_context) # Use chat function
                                else:
                                    logger.error(f"[{addr}] No text input available for Gemini on attempt {attempt + 1} (Method: {method}, IsRetry: {is_retry}).")
                                    script = None
                                    break # No text to process
                            else:
                                logger.error(f"[{addr}] Unknown method '{method}' in pending request {request_id}.")
                                script = None
                                break # Unknown method, stop trying

                            # --- Check script validity ---
                            is_valid_script = script and script.strip() and "# Error:" not in script
                            if is_valid_script:
                                logger.info(f"[{addr}] Successfully generated script on attempt {attempt + 1} for request {request_id}.")
                                break # Exit retry loop on success
                            else:
                                logger.warning(f"[{addr}] Script generation attempt {attempt + 1} failed for request {request_id}. Script: '{script}'")
                                if attempt < max_retries - 1:
                                    time.sleep(0.5) # Small delay before retry
                                # Loop continues for the next attempt

                        # --- After loop ---
                        # Determine final response status based on the final state of 'script'
                        if script and script.strip() and "# Error:" not in script:
                            response_status = "script"
                            response_message = "Generated script"
                             # Log the actual script content (Corrected Indentation)
                            logger.debug(f"[{addr}] Generated script content for request {request_id}:\n```python\n{script}\n```")
                        else:
                            response_status = "error"
                            response_message = f"Script generation failed (Request ID: {request_id}): Gemini could not process the command or returned an error."
                            logger.warning(f"[{addr}] Failed to generate valid script for request {request_id}. Original text: '{original_text}'")

                        # Send response block (Corrected Indentation - should be outside the if/else)
                        try:
                            # Log before sending
                            logger.debug(f"[{addr}] Attempting to send {response_status} response for request {request_id}...")
                            conn.sendall(json.dumps({
                                "status": response_status, "message": response_message,
                                "script": script, # Send None if script generation failed
                                "request_id": request_id,
                                "original_text": original_text # Essential for history
                            }).encode())
                            # Log after successful send
                            logger.debug(f"[{addr}] Successfully sent {response_status} response for request {request_id}.")
                        except socket.error as send_err:
                            logger.error(f"[{addr}] Failed to send {response_status} response for request {request_id}: {send_err}")

                    # This else corresponds to the `if request_id in pending_context_requests:` check
                    else:
                        logger.warning(f"[{addr}] Received context response for unknown/expired request ID: {request_id}")

                elif msg_type == "process_text":
                    text_to_process = client_message.get("text")
                    context_for_text = client_message.get("context")
                    request_id_text = str(uuid.uuid4()) # Generate ID for this text request

                    if conn not in client_configs:
                         logger.warning(f"[{addr}] Received 'process_text' but client not configured. Ignoring.")
                         try: conn.sendall(json.dumps({"status":"error", "message":"Client not configured.", "request_id": request_id_text, "original_text": text_to_process}).encode())
                         except: pass
                         continue

                    # --- Get Chat Session ---
                    chat_session = client_chat_sessions.get(conn)
                    if not chat_session:
                         logger.error(f"[{addr}] No chat session found for connection during process_text {request_id_text}. Cannot proceed.")
                         try:
                             conn.sendall(json.dumps({"status":"error", "message":"Chat session missing on server.", "request_id": request_id_text, "original_text": text_to_process}).encode())
                         except: pass
                         continue

                    config = client_configs[conn]
                    model_name = config.get('model_name') # Model name needed for logging/potential future use

                    if text_to_process and model_name:
                        logger.info(f"[{addr}] Processing direct text command via chat (ID: {request_id_text})...")
                        script = None
                        max_retries_text = 2 # Keep retry logic for generation failures

                        for attempt_text in range(max_retries_text):
                            logger.info(f"[{addr}] Text script generation attempt {attempt_text + 1}/{max_retries_text} for request {request_id_text}")
                            prompt_for_gemini_text = ""
                            is_retry_text = False

                            # Check for reported execution error (less likely for text, but possible)
                            reported_error_text = execution_errors.pop(request_id_text, None)

                            if reported_error_text:
                                is_retry_text = True
                                logger.info(f"[{addr}] Retrying text request {request_id_text} due to reported execution error.")
                                error_type = reported_error_text['error_type']
                                error_msg = reported_error_text['error_message']
                                prompt_for_gemini_text = f"""
**Previous Script Failed Execution in Blender:**
The script generated for the command '{text_to_process}' failed with the following error:
```
{error_type}: {error_msg}
```
**Please analyze the original command and the execution error, then generate a corrected Blender 4.x Python script.**

**Instructions:** (Same as before - prioritize bpy.data, etc.)
1.  **Fix the Error:** Address the specific `{error_type}` reported.
2.  **Output Python Code Only:** Your response must contain ONLY the Python script.
3.  **Use Blender 4.x API.**
4.  **Prioritize `bpy.data`.**

**Original Command:** {text_to_process}
**Current Blender Context:**
{format_blender_context(context_for_text)}

**Corrected Script:**
"""
                            elif attempt_text > 0: # Retry on initial generation failure
                                is_retry_text = True
                                logger.info(f"[{addr}] Retrying text request {request_id_text} due to initial generation failure.")
                                prompt_for_gemini_text = f"""
**Previous Generation Attempt Failed:**
The previous attempt to generate a script for the command '{text_to_process}' failed (returned no script or an error comment).
**Please analyze the original command and try again.** (Instructions remain the same)

**Original Command:** {text_to_process}
**Current Blender Context:**
{format_blender_context(context_for_text)}

**Script:**
"""
                            else:
                                # First attempt - construct standard prompt for text
                                prompt_for_gemini_text = f"""
**Command:** {text_to_process}
**Current Blender Context:**
{format_blender_context(context_for_text)}

**Instructions:** (Same as before - prioritize bpy.data, etc.)
1.  **Output Python Code Only.**
2.  **Use Blender 4.x API.**
3.  **Prioritize `bpy.data`.**
4.  **Consider History:** Remember previous commands/responses in this chat.
5.  **Handle Errors:** If unclear/complex, output `# Error: Command cannot be processed.`

**Script:**
"""

                            # Call Gemini using the CHAT SESSION
                            script = process_text_with_chat(chat_session, prompt_for_gemini_text, context_for_text) # Use chat function


                            # --- Check script validity ---
                            is_valid_script_text = script and script.strip() and "# Error:" not in script
                            if is_valid_script_text:
                                logger.info(f"[{addr}] Successfully generated script from text on attempt {attempt_text + 1} for request {request_id_text}.")
                                break # Exit retry loop on success
                            else:
                                logger.warning(f"[{addr}] Text script generation attempt {attempt_text + 1} failed for request {request_id_text}. Script: '{script}'")
                                if attempt_text < max_retries_text - 1:
                                    time.sleep(0.5) # Small delay before retry
                                # Loop continues for the next attempt

                        # --- After loop ---
                        # Determine final response status based on the final state of 'script'
                        if script and script.strip() and "# Error:" not in script:
                            response_status_text = "script"
                            response_message_text = "Generated script from text"
                             # Log the actual script content (Corrected Indentation)
                            logger.debug(f"[{addr}] Generated script content for text request {request_id_text}:\n```python\n{script}\n```")
                        else:
                            response_status_text = "error"
                            response_message_text = f"Failed to generate script from text (Request ID: {request_id_text}): Gemini could not process the command or returned an error."
                            logger.warning(f"[{addr}] Failed to generate valid script for text request {request_id_text}. Original text: '{text_to_process}'")

                        # Send response block (Corrected Indentation - should be outside the if/else)
                        try:
                             # Log before sending
                            logger.debug(f"[{addr}] Attempting to send {response_status_text} response for text request {request_id_text}...")
                            conn.sendall(json.dumps({
                                "status": response_status_text, "message": response_message_text,
                                "script": script, # Send None if script generation failed
                                "request_id": request_id_text, # Send the unique ID for this text request
                                "original_text": text_to_process # Essential for history
                            }).encode())
                            # Log after successful send
                            logger.debug(f"[{addr}] Successfully sent {response_status_text} response for text request {request_id_text}.")
                        except socket.error as send_err:
                            logger.error(f"[{addr}] Failed to send {response_status_text} response for text request {request_id_text}: {send_err}")

                    # This else corresponds to the `if text_to_process and model_name:` check
                    else:
                        error_detail = "Missing text command." if not text_to_process else "Model name not configured."
                        logger.warning(f"[{addr}] Invalid 'process_text' request: {error_detail} - Message: {client_message}")
                        try: conn.sendall(json.dumps({"status":"error", "message": f"Invalid text command: {error_detail}", "request_id": request_id_text, "original_text": text_to_process}).encode())
                        except: pass

                else:
                    logger.warning(f"[{addr}] Received unknown message type: '{msg_type}'")
                    try: conn.sendall(json.dumps({"status":"error", "message": f"Unknown message type '{msg_type}' received."}).encode())
                    except: pass

            except json.JSONDecodeError: logger.error(f"[{addr}] Failed to decode JSON from client: {client_data!r}")
            except UnicodeDecodeError: logger.error(f"[{addr}] Failed to decode client data as UTF-8: {client_data!r}")
            except Exception as msg_proc_err:
                logger.error(f"[{addr}] Error processing client message: {type(msg_proc_err).__name__} - {msg_proc_err}", exc_info=True)
                # Consider breaking here too? Depends on error type. For now, let loop continue/retry.

        except socket.timeout:
            # logger.debug(f"[{addr}] Socket recv timed out. Continuing loop.") # Removed noisy log
            continue
        except (socket.error, ConnectionResetError, BrokenPipeError) as sock_err:
            logger.warning(f"[{addr}] Socket error in handler loop (client likely disconnected): {type(sock_err).__name__} - {sock_err}")
            logger.debug(f"[{addr}] Breaking handler loop due to socket error.")
            # --- Start Cleanup ---
            logger.info(f"[{addr}] Performing cleanup for handler thread due to socket error.")
            if conn in client_configs:
                try: del client_configs[conn]
                except KeyError: pass
                logger.debug(f"[{addr}] Removed client config during cleanup.")
            # Also clear chat session for this client
            if conn in client_chat_sessions:
                try: del client_chat_sessions[conn]
                except KeyError: pass
                logger.debug(f"[{addr}] Removed client chat session during cleanup.")

            requests_to_remove = [req_id for req_id, data in pending_context_requests.items() if data.get('conn') == conn]
            for req_id in requests_to_remove:
                try: del pending_context_requests[req_id]
                except KeyError: pass
            if requests_to_remove: logger.debug(f"[{addr}] Removed {len(requests_to_remove)} pending context requests during cleanup.")
            # Also clear any execution errors for this client
            errors_to_remove = [req_id for req_id, err_data in execution_errors.items() if err_data.get('conn') == conn]
            for req_id in errors_to_remove:
                 try: del execution_errors[req_id]
                 except KeyError: pass
            if errors_to_remove: logger.debug(f"[{addr}] Removed {len(errors_to_remove)} execution errors during cleanup.")


            close_socket(conn, addr)
            # --- End Cleanup ---
            break
        except Exception as e:
            logger.error(f"[{addr}] Unexpected error in message handler loop: {type(e).__name__} - {e}", exc_info=True)
            logger.debug(f"[{addr}] Breaking handler loop due to unexpected error.")
            # --- Start Cleanup ---
            logger.info(f"[{addr}] Performing cleanup for handler thread due to unexpected error.")
            if conn in client_configs:
                try: del client_configs[conn]
                except KeyError: pass
                logger.debug(f"[{addr}] Removed client config during cleanup.")
            # Also clear chat session for this client
            if conn in client_chat_sessions:
                try: del client_chat_sessions[conn]
                except KeyError: pass
                logger.debug(f"[{addr}] Removed client chat session during cleanup.")

            requests_to_remove = [req_id for req_id, data in pending_context_requests.items() if data.get('conn') == conn]
            for req_id in requests_to_remove:
                try: del pending_context_requests[req_id]
                except KeyError: pass
            if requests_to_remove: logger.debug(f"[{addr}] Removed {len(requests_to_remove)} pending context requests during cleanup.")

            close_socket(conn, addr)
            # --- End Cleanup ---
            break
        # logger.debug(f"[{addr}] Reached end of handler loop try/except block.") # Might be noisy

    # --- Cleanup after loop finishes normally (e.g., stop_server set) ---
    logger.info(f"[{addr}] Handler loop finished (stop_server set?). Performing final cleanup.")
    if conn in client_configs:
        try: del client_configs[conn]
        except KeyError: pass
        logger.debug(f"[{addr}] Removed client config during final cleanup.")
    # Also clear chat session for this client
    if conn in client_chat_sessions:
        try: del client_chat_sessions[conn]
        except KeyError: pass
        logger.debug(f"[{addr}] Removed client chat session during final cleanup.")

    requests_to_remove = [req_id for req_id, data in pending_context_requests.items() if data.get('conn') == conn]
    for req_id in requests_to_remove:
        try: del pending_context_requests[req_id]
        except KeyError: pass
    if requests_to_remove: logger.debug(f"[{addr}] Removed {len(requests_to_remove)} pending context requests during final cleanup.")
    # Also clear any execution errors for this client
    errors_to_remove = [req_id for req_id, err_data in execution_errors.items() if err_data.get('conn') == conn]
    for req_id in errors_to_remove:
        try: del execution_errors[req_id]
        except KeyError: pass
    if errors_to_remove: logger.debug(f"[{addr}] Removed {len(errors_to_remove)} execution errors during final cleanup.")

    close_socket(conn, addr)
    logger.info(f"[{addr}] Message handler thread function exiting.")


def is_socket_connected(sock: socket.socket) -> bool:
    """Checks if a socket is likely still connected."""
    if not sock or sock.fileno() == -1: return False
    try:
        sock.settimeout(0.01) # Very short timeout
        # Sending 0 bytes should succeed on connected sockets, fail otherwise
        sock.send(b'')
        return True
    except (BlockingIOError, InterruptedError): return True # Ok if it would block
    except (ConnectionResetError, BrokenPipeError, socket.error, OSError): return False # Definitively disconnected
    except Exception as e:
         logger.warning(f"Unexpected error checking socket status: {e}")
         return False
    finally:
        try: sock.settimeout(None) # Reset to blocking
        except: pass

def close_socket(sock: socket.socket, addr):
    """Gracefully close a client socket."""
    if sock and sock.fileno() != -1:
        logger.debug(f"[{addr}] Closing socket connection.")
        try: sock.shutdown(socket.SHUT_RDWR)
        except (socket.error, OSError) as e:
            if e.errno not in [107, 9, 57]: pass # Ignore "not connected", "bad fd", "Socket is not connected"
            else: logger.warning(f"[{addr}] Error during socket shutdown: {type(e).__name__} - {e}")
        finally:
            try: sock.close()
            except Exception as e: logger.warning(f"[{addr}] Error during socket close: {e}")

# --- Main Server Function ---
def start_standalone_voice_recognition_server():
    """Starts the main server listening loop."""
    if not DEPENDENCIES_INSTALLED:
        logger.critical("Cannot start server due to missing core dependencies.")
        return
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.critical("GEMINI_API_KEY is not configured. Server cannot start.")
        return

    threads = []
    server_socket = None
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        logger.info(f"Server listening on {HOST}:{PORT}")
        logger.info("Waiting for Blender client connection...")

        while not stop_server.is_set():
            try:
                server_socket.settimeout(1.0)
                conn, addr = server_socket.accept()
                conn.settimeout(None)
                addr_str = f"{addr[0]}:{addr[1]}"
                logger.info(f"Connection accepted from {addr_str}")

                handler_thread = threading.Thread(target=client_message_handler_thread, args=(conn, addr_str), name=f"Handler-{addr_str}", daemon=True)
                handler_thread.start()
                threads.append(handler_thread)

                # Start listener thread immediately after handler
                # Start the NEW listener thread
                listener_thread = threading.Thread(target=server_audio_listener_thread, args=(conn, addr_str), name=f"Listener-Vosk-{addr_str}", daemon=True)
                listener_thread.start()
                threads.append(listener_thread)

                # Keep the old one commented out for now
                # listener_thread_sr = threading.Thread(target=server_audio_listener_thread_speechrecognition, args=(conn, addr_str), name=f"Listener-SR-{addr_str}", daemon=True)
                # listener_thread_sr.start()
                # threads.append(listener_thread_sr)

            except socket.timeout: continue
            except OSError as e:
                 if e.errno in [98, 10048]: logger.critical(f"Failed to bind to {HOST}:{PORT}. Address already in use. Shutting down.")
                 else: logger.error(f"Server OS error during accept/bind: {e}", exc_info=True)
                 stop_server.set(); break
            except Exception as accept_err:
                if not stop_server.is_set(): logger.error(f"Error accepting connection: {accept_err}", exc_info=True)
                time.sleep(1)

    except OSError as e:
         if e.errno in [98, 10048]: logger.critical(f"Failed to bind server to {HOST}:{PORT}. Address already in use.")
         else: logger.error(f"Server OS error during initial setup: {e}", exc_info=True)
    except Exception as e: logger.error(f"Server error before accept loop: {e}", exc_info=True)
    finally:
        logger.info("Server shutting down...")
        stop_server.set()
        if server_socket:
             try: server_socket.close(); logger.info("Server listening socket closed.")
             except Exception as close_err: logger.warning(f"Error closing server socket: {close_err}")

        join_timeout = 3.0
        logger.info(f"Waiting up to {join_timeout}s for client threads to finish...")
        # Get threads associated with this server run more reliably
        current_pid = os.getpid()
        # This is tricky; joining daemon threads isn't always straightforward.
        # The finally block in each thread function handles cleanup.
        # Give them time to see the stop_server event.
        time.sleep(join_timeout)

        # Clear global state
        pending_context_requests.clear(); client_configs.clear(); execution_errors.clear(); client_chat_sessions.clear() # Added chat sessions cleanup
        logger.info("Server shutdown complete.")

if __name__ == "__main__":
    logger.info(f"Executing __main__ block (Version: {CODE_VERSION})")
    try:
        start_standalone_voice_recognition_server()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, initiating server shutdown...")
        if not stop_server.is_set(): stop_server.set()
    except Exception as main_err:
         logger.critical(f"Critical error in main execution: {main_err}", exc_info=True)
         if not stop_server.is_set(): stop_server.set()
    finally:
        if not stop_server.is_set(): stop_server.set()
        time.sleep(0.5) # Allow final cleanup
        logger.info("Server script main execution finished.")
