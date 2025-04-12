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

# --- Diagnostic Prints (Optional: Remove after confirming fix) ---
# import sys
# import os
# print(f"--- Python Executable: {sys.executable}")
# print(f"--- Working Directory: {os.getcwd()}")
# print("--- sys.path ---")
# for p in sys.path:
#     print(p)
# print("--- End sys.path ---")
# try:
#     import google.generativeai
#     print("--- Successfully imported google.generativeai ---")
# except ImportError as e:
#     print(f"--- FAILED to import google.generativeai: {e} ---")
# --- End Diagnostic Prints ---


# --- Logging Setup ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_file = Path(__file__).parent.parent / 'articulate3d_server.log' # Log file in project root

# Configure root logger for console output
# Set level to DEBUG to see the detailed logs we are adding
logging.basicConfig(level=logging.DEBUG, format=log_format, handlers=[logging.StreamHandler(sys.stdout)])

# Create a specific logger for this module
logger = logging.getLogger(__name__) # Use __name__ for logger name
# Ensure this logger also captures DEBUG level messages
logger.setLevel(logging.DEBUG)

# Add file handler
try:
    file_handler = logging.FileHandler(log_file, mode='a') # Use append mode
    file_handler.setFormatter(logging.Formatter(log_format))
    # Set file handler level to DEBUG as well
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    # Prevent logs from propagating to the root logger if handlers are added here
    logger.propagate = False
    logger.info(f"--- Log session started. Logging to {log_file} ---")
except Exception as e:
    # Use root logger if specific logger fails during setup
    logging.error(f"Failed to set up file logging to {log_file}: {e}")

# --- End Logging Setup ---


# Try to import dotenv with better error handling
try:
    import dotenv
    # Load environment variables from .env file if it exists
    project_root = Path(__file__).parent.parent
    env_path = project_root / '.env'
    if env_path.exists():
        logger.info(f"Loading environment variables from {env_path}")
        dotenv.load_dotenv(env_path)
    else:
        logger.info(".env file not found, relying on system environment variables.")
except ImportError:
    logger.warning("python-dotenv module not found. Environment variables will not be loaded from .env file.")
    logger.warning("Please run setup.py to install required dependencies.")

# --- CORRECTED Import for AI and Audio libraries ---
try:
    # Use the standard import convention for the library
    import google.generativeai as genai
    # Remove the specific types import: from google.generativeai import types as genai_types
    import whisper
    from google.cloud import speech
    import speech_recognition as sr # Keep for now, might be used by client or for reference
    import pyaudio # Keep for now
    DEPENDENCIES_INSTALLED = True
    logger.debug("Successfully imported core AI/Audio libraries.")
except ImportError as e:
    DEPENDENCIES_INSTALLED = False
    # Log the specific import error encountered
    logger.critical(f"Required dependencies not installed: {e}. Please run setup.py first.")
    # Exit if core dependencies are missing
    if "google.generativeai" in str(e) or "whisper" in str(e) or "google.cloud" in str(e):
         sys.exit(1)
# --- End CORRECTED Import ---


# Socket server configuration
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

# Flag to signal the server to stop
stop_server = threading.Event()

def format_blender_context(context_data):
    """Formats the received Blender context dictionary into a string for the prompt."""
    if not context_data:
        return "No Blender context provided."

    mode = context_data.get('mode', 'UNKNOWN')
    active = context_data.get('active_object', 'None')
    selected = context_data.get('selected_objects', [])

    # Create a concise string representation
    context_str = f"Current Blender context: Mode={mode}, Active Object={active}, Selected Objects={selected}"
    return context_str

# Updated for google.generativeai SDK usage
def process_text_with_gemini(client: genai.GenerativeModel, text: str, model_name: str, blender_context: dict = None):
    """Process transcribed text with Gemini API, using Blender context."""
    # Type hint uses genai.GenerativeModel which should now resolve correctly
    try:
        logger.debug(f"Processing text with Gemini model: {model_name}")

        # --- Format Received Context ---
        context_info = format_blender_context(blender_context)
        logger.debug(f"Using context: {context_info}") # Context info is not used in the prompt yet, but logged

        # --- Revised Prompt Structure ---
        prompt = f"""
You are a Blender 4.x Python script generator.
Translate the following command into a `bpy` Python script compatible with Blender 4.x.

**Instructions:**
1.  **Output Python Code Only:** Your response must contain ONLY the Python script. Do not include ```python, explanations, comments, introductions, or any other text.
2.  **Use Blender 4.x API:** Ensure the script uses `bpy` commands compatible with Blender 4.x.
3.  **Handle Errors:** If the command is unclear, too complex to translate reliably, or potentially unsafe, output ONLY the following line:
    `# Error: Command cannot be processed.`

**Command:** {text}

**Script:**
"""
        # logger.debug(f"Sending prompt to Gemini:\n{prompt}") # Log the full prompt for debugging

        # Configure generation settings as a dictionary
        generation_config = {
            "temperature": 0.2,
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 2048,
        }

        # Configure safety settings using genai.types
        # Use dictionary format consistent with client_message_handler_thread
        safety_settings = [
            {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
        ]

        # --- Debug Logging before Text API Call ---
        logger.debug(f"[Text] Attempting generate_content for model: {model_name}")
        logger.debug(f"[Text] Client object type: {type(client)}")
        logger.debug(f"[Text] Contents type: {type(prompt)}")
        # logger.debug(f"[Text] Contents value:\n{prompt}") # Avoid logging potentially large prompts unless necessary
        logger.debug(f"[Text] Generation config type: {type(generation_config)}")
        logger.debug(f"[Text] Generation config value: {generation_config}")
        logger.debug(f"[Text] Safety settings type: {type(safety_settings)}")
        logger.debug(f"[Text] Safety settings value: {safety_settings}")
        # --- End Debug Logging ---

        # Generate the response using the provided client instance (GenerativeModel)
        # Configs are now passed during model initialization for this library version
        response = client.generate_content(
            contents=prompt
        )

        # Extract the script from the response
        script = ""
        if response.parts:
            script = response.parts[0].text.strip()
        elif hasattr(response, 'text'): # Check for direct text attribute as fallback
             script = response.text.strip()
        else:
            logger.warning("[Text] Gemini response did not contain expected text part.")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                 logger.warning(f"[Text] Gemini request blocked: {response.prompt_feedback.block_reason}")

        logger.info("[Text] Received script from Gemini.")
        # logger.debug(f"[Text] Generated Script Snippet: {script[:100]}...") # Log snippet

        return script
    except Exception as e:
        logger.error(f"Error processing text with Gemini: {e}", exc_info=True) # Log traceback
        return None # Return None on error

# --- New Processing Functions ---

# Global cache for Whisper model
whisper_model_cache = {}

def transcribe_with_whisper(audio_bytes: bytes) -> str | None:
    """Transcribe audio using OpenAI Whisper."""
    global whisper_model_cache
    
    model_name = "small" # Using 'base' model as decided
    try:
        if model_name not in whisper_model_cache:
            logger.info(f"Loading Whisper model: {model_name}...")
            whisper_model_cache[model_name] = whisper.load_model(model_name)
            logger.info("Whisper model loaded.")

        model = whisper_model_cache[model_name]

        # --- Use temporary file within project directory ---
        tmp_file_path = None # Initialize path variable
        try:
            # Define and ensure the temp audio directory exists within the addon
            addon_dir = Path(__file__).parent.parent # Go up two levels from src/
            temp_audio_dir = addon_dir / "temp_audio"
            os.makedirs(temp_audio_dir, exist_ok=True)
            logger.debug(f"Ensured temp audio directory exists: {temp_audio_dir}")

            # Use NamedTemporaryFile within the project's temp_audio directory
            # Set delete=False initially, we will manually delete in finally block
            with tempfile.NamedTemporaryFile(dir=temp_audio_dir, suffix=".wav", delete=False) as tmp_file:
                tmp_file_path = tmp_file.name # Store the path
                # Assuming audio_bytes is already in WAV format
                tmp_file.write(audio_bytes)
                # File handle is automatically closed when exiting 'with' block

            logger.debug(f"Created temporary WAV file: {tmp_file_path}")

            # Transcribe using the file path (file is now closed)
            logger.debug(f"Transcribing with Whisper using temp file path: {tmp_file_path}")
            result = model.transcribe(tmp_file_path)
            text = result.get("text", "").strip()
            logger.info(f"Whisper transcription result: {text}")
            return text

        except Exception as e:
            # Catch errors during transcription processing
            logger.error(f"Error during Whisper transcription processing step: {e}", exc_info=True)
            if isinstance(e, RuntimeError) and "ffmpeg" in str(e).lower():
                 logger.error("This might be an ffmpeg issue. Ensure ffmpeg is installed, in PATH, and can access the temp file.")
            return None
        finally:
            # Ensure temporary file is deleted even if transcription fails
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                    logger.debug(f"Deleted temporary file: {tmp_file_path}")
                except OSError as e_del:
                    logger.error(f"Error deleting temporary file {tmp_file_path}: {e_del}")

    # Catch errors during model loading or initial setup
    except Exception as e:
        logger.error(f"Error setting up Whisper transcription (model loading?): {e}", exc_info=True)
        return None


def transcribe_with_google_stt(audio_bytes: bytes, sample_rate: int = 16000) -> str | None:
    """Transcribe audio using Google Cloud Speech-to-Text."""
    try:
        logger.info("Transcribing with Google Cloud STT...")
        # Requires GOOGLE_APPLICATION_CREDENTIALS env var to be set
        client = speech.SpeechClient()

        # Assuming LINEAR16 encoding, common for WAV
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate, # Get sample rate from client if possible
            language_code="en-US", # Make configurable?
        )

        response = client.recognize(config=config, audio=audio)

        if not response.results:
            logger.warning("Google Cloud STT returned no results.")
            return None

        transcript = "".join(result.alternatives[0].transcript for result in response.results if result.alternatives)
        logger.info(f"Google Cloud STT transcription result: {transcript}")
        return transcript

    except Exception as e:
        logger.error(f"Error during Google Cloud STT transcription: {e}", exc_info=True)
        return None

def process_audio_with_gemini(client: genai.GenerativeModel, audio_bytes: bytes, model_name: str, blender_context: dict = None, mime_type: str = "audio/wav") -> str | None:
    """Process audio directly with Gemini API, using Blender context."""
    # Type hint uses genai.GenerativeModel
    try:
        logger.debug(f"Processing audio directly with Gemini model: {model_name}")

        context_info = format_blender_context(blender_context)
        logger.debug(f"Using context: {context_info}")

        # --- Prompt for Audio Input ---
        prompt = f"""
You are a Blender 4.x Python script generator.
Listen to the following audio command and translate it into a `bpy` Python script compatible with Blender 4.x.

**Instructions:**
1.  **Output Python Code Only:** Your response must contain ONLY the Python script. Do not include ```python, explanations, comments, introductions, or any other text.
2.  **Use Blender 4.x API:** Ensure the script uses `bpy` commands compatible with Blender 4.x.
3.  **Handle Errors:** If the command is unclear, too complex to translate reliably, or potentially unsafe, output ONLY the following line:
    `# Error: Command cannot be processed.`

**Script:**
"""
        # logger.debug(f"Sending audio prompt to Gemini:\n{prompt}")

        # Prepare audio data using genai.types
        # Use Part.from_data for modern SDK versions
        audio_part = genai.types.Part.from_data(data=audio_bytes, mime_type=mime_type)

        # Configure generation settings as a dictionary
        generation_config = { # Renamed from generation_config_obj
            "temperature": 0.2, # May need different tuning for audio
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
        # Configure safety settings using genai.types
        # Use dictionary format consistent with client_message_handler_thread
        safety_settings_list = [
            {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
        ]

        # --- Start Detailed Debug Logging ---
        logger.debug(f"[Audio] Attempting generate_content for model: {model_name}")
        logger.debug(f"[Audio] Client object type: {type(client)}")
        # Prepare contents list for logging and the actual call
        contents_list = [prompt, audio_part]
        try:
             logger.debug(f"[Audio] Contents type: {type(contents_list)}")
             logger.debug(f"[Audio] Contents length: {len(contents_list)}")
             logger.debug(f"[Audio]   Prompt type: {type(contents_list[0])}")
             logger.debug(f"[Audio]   Audio part type: {type(contents_list[1])}")
             # Avoid logging full audio bytes, log size instead
             if hasattr(contents_list[1], 'data'):
                 logger.debug(f"[Audio]   Audio data size: {len(contents_list[1].data)} bytes")
                 logger.debug(f"[Audio]   Audio mime_type: {contents_list[1].mime_type}")
             else:
                 # This case shouldn't happen if using Part.from_data correctly
                 logger.warning("[Audio]   Audio part doesn't have 'data' attribute as expected.")
        except Exception as log_e:
             logger.error(f"[Audio] Error logging contents details: {log_e}")

        logger.debug(f"[Audio] Generation config type: {type(generation_config)}")
        logger.debug(f"[Audio] Generation config value: {generation_config}")
        logger.debug(f"[Audio] Safety settings type: {type(safety_settings_list)}")
        logger.debug(f"[Audio] Safety settings value: {safety_settings_list}")
        # --- End Detailed Debug Logging ---

        # Pass generation_config and safety_settings directly as keyword arguments
        # Use the contents_list prepared above
        # Configs are now passed during model initialization for this library version
        response = client.generate_content(
            contents=contents_list      # List contains text prompt and audio data part
        )

        # Check if response has text part before accessing .text
        script = ""
        if response.parts:
            script = response.parts[0].text.strip() # Assuming the script is in the first part
        elif hasattr(response, 'text'): # Check for direct text attribute as fallback
             script = response.text.strip()
        else:
            logger.warning("[Audio] Gemini response did not contain expected text part.")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                 logger.warning(f"[Audio] Gemini request blocked: {response.prompt_feedback.block_reason}")

        logger.info("[Audio] Received script from Gemini.")
        # logger.debug(f"[Audio] Generated Script Snippet: {script[:100]}...")
        return script

    except Exception as e:
        logger.error(f"Error processing audio with Gemini: {e}", exc_info=True)
        return None

# --- End New Processing Functions ---

# Dictionary to hold data while waiting for context response from client
pending_context_requests = {}
# Dictionary to hold client configuration per connection
client_configs = {} # Stores {'model_name': str, 'method': str, 'genai_model_instance': genai.GenerativeModel | None}

# Thread function for server-side audio listening
def server_audio_listener_thread(conn, addr):
    """Thread function to handle continuous voice recognition from server mic."""
    logger.info(f"[{addr}] Audio listener thread started.")
    recognizer = sr.Recognizer()
    mic_index = None # Use default microphone

    try:
        with sr.Microphone(device_index=mic_index) as source:
            logger.info(f"[{addr}] Adjusting for ambient noise...")
            try:
                conn.sendall(json.dumps({"status": "info", "message": "Adjusting for ambient noise..."}).encode())
            except socket.error as send_err:
                 logger.warning(f"[{addr}] Failed to send 'adjusting noise' status: {send_err}")

            recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.info(f"[{addr}] Ready to listen.")
            try:
                conn.sendall(json.dumps({"status": "info", "message": "Listening..."}).encode())
            except socket.error as send_err:
                 logger.warning(f"[{addr}] Failed to send 'listening' status: {send_err}")


            while not stop_server.is_set():
                if conn.fileno() == -1: # Check if socket is closed
                    logger.warning(f"[{addr}] Connection closed in listener loop.")
                    break

                if conn not in client_configs:
                    # logger.debug(f"[{addr}] No configuration received yet. Waiting...") # Reduce log noise
                    time.sleep(1)
                    continue

                try:
                    config = client_configs[conn].copy()
                except KeyError:
                    logger.warning(f"[{addr}] Config removed unexpectedly. Waiting...")
                    time.sleep(1)
                    continue

                current_model_name = config.get('model_name', 'gemini-2.0-flash') # Use updated default
                current_method = config.get('method', 'whisper') # Default if not set

                try:
                    # logger.debug(f"[{addr}] Listening for audio...") # Reduce log noise
                    audio = recognizer.listen(source, timeout=2, phrase_time_limit=10) # Shorter timeout

                    if stop_server.is_set(): break

                    logger.info(f"[{addr}] Audio detected, processing with method: {current_method}")
                    audio_bytes = audio.get_wav_data() # Get raw WAV data
                    request_id = str(uuid.uuid4())
                    text_result = None
                    audio_to_process = None

                    if current_method == "gemini":
                        audio_to_process = audio_bytes
                        message_to_client = "Processing audio..."
                    elif current_method == "whisper":
                        text_result = transcribe_with_whisper(audio_bytes)
                        message_to_client = f"Transcribed (Whisper): {text_result}" if text_result else "Whisper transcription failed."
                    elif current_method == "google_stt":
                        text_result = transcribe_with_google_stt(audio_bytes)
                        message_to_client = f"Transcribed (Google STT): {text_result}" if text_result else "Google STT transcription failed."
                    else:
                        logger.error(f"[{addr}] Unknown audio method: {current_method}")
                        continue # Skip processing

                    pending_context_requests[request_id] = {
                        'audio_bytes': audio_to_process,
                        'text': text_result,
                        'model_name': current_model_name,
                        'method': current_method,
                        'conn': conn,
                        'addr': addr
                    }
                    logger.debug(f"[{addr}] Stored pending request {request_id} for method {current_method}")

                    try:
                        conn.sendall(json.dumps({
                            "status": "request_context",
                            "request_id": request_id,
                            "message": message_to_client
                        }).encode())
                        logger.debug(f"[{addr}] Sent context request {request_id} to client.")
                    except socket.error as send_err:
                        logger.error(f"[{addr}] Failed to send context request {request_id}: {send_err}")
                        if request_id in pending_context_requests:
                            del pending_context_requests[request_id]

                except sr.WaitTimeoutError:
                    # logger.debug(f"[{addr}] Listen timeout, continuing...") # Reduce log noise
                    pass # Normal timeout, continue loop
                except Exception as e:
                    logger.error(f"[{addr}] Error in listening loop: {e}", exc_info=True)
                    try: conn.sendall(json.dumps({"status": "error", "message": f"Listener error: {e}"}).encode())
                    except: pass
                    time.sleep(1) # Avoid tight loop on persistent error

    except sr.RequestError as e:
        logger.error(f"[{addr}] Speech Recognition API request failed: {e}")
        try: conn.sendall(json.dumps({"status": "error", "message": f"Speech Recognition API error: {e}"}).encode())
        except: pass
    except Exception as e:
        logger.error(f"[{addr}] Error initializing microphone or recognizer: {e}", exc_info=True)
        try: conn.sendall(json.dumps({"status": "error", "message": f"Mic/Recognizer init error: {e}"}).encode())
        except: pass
    finally:
        logger.info(f"[{addr}] Audio listener thread finished.")
        if conn in client_configs:
            try:
                del client_configs[conn]
            except KeyError:
                 logger.debug(f"[{addr}] Config already removed for connection.")


# Thread function to handle incoming messages from the client
def client_message_handler_thread(conn, addr, api_key): # Added addr for logging
    logger.info(f"[{addr}] Client message handler thread started.")
    try:
        # Configure the genai library globally with the API key
        try:
            genai.configure(api_key=api_key)
            logger.info(f"[{addr}] genai library configured with API key.")
            # Send ready message
            conn.sendall(json.dumps({"status": "ready", "message": "Server ready and connected."}).encode())
        except Exception as e:
            logger.error(f"[{addr}] Failed to configure genai library: {e}", exc_info=True)
            try:
                conn.sendall(json.dumps({"status": "error", "message": f"Server error: Failed Gemini init: {e}"}).encode())
            except socket.error: pass # Ignore if cannot send error
            return # Exit thread if library cannot be configured

        while not stop_server.is_set():
            try:
                conn.settimeout(0.5)
                client_data = conn.recv(4096) # Increased buffer size
                if not client_data:
                    logger.info(f"[{addr}] Client disconnected.")
                    break # Exit if client closes connection

                try:
                    client_message = json.loads(client_data.decode())
                    logger.debug(f"[{addr}] Received message: {client_message}")
                    msg_type = client_message.get("type")

                    # --- Handle Configuration ---
                    if msg_type == "configure":
                        model_name = client_message.get("model")
                        method = client_message.get("method")
                        if model_name and method:
                            try:
                                # Define generation and safety settings before initializing model
                                # Use dictionary format for generation_config
                                generation_config = {
                                    "temperature": 0.2,
                                    "top_p": 0.8,
                                    "top_k": 40,
                                    "max_output_tokens":2048,
                                }
                                
                                # Define safety_settings as dictionaries for older library versions
                                safety_settings = [
                                    {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                                    {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                                    {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                                    {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
                                ]
                                logger.debug(f"[{addr}] Defined generation_config: {generation_config}")
                                logger.debug(f"[{addr}] Defined safety_settings (dict format): {safety_settings}")

                                # Initialize the specific Gemini Model instance using genai, passing configs
                                logger.debug(f"[{addr}] Attempting to initialize GenerativeModel: {model_name} with configs")
                                model_instance = genai.GenerativeModel(
                                    model_name,
                                    generation_config=generation_config,
                                    safety_settings=safety_settings
                                )
                                logger.info(f"[{addr}] Initialized Gemini Model instance for: {model_name} with specific configs.")

                                # Store config globally associated with the connection object
                                client_configs[conn] = {
                                    "model_name": model_name,
                                    "method": method,
                                    "genai_model_instance": model_instance # Store the instance
                                }
                                logger.info(f"[{addr}] Configured: Model={model_name}, Method={method}")
                                # Send confirmation back to client
                                try:
                                     conn.sendall(json.dumps({"status": "info", "message": f"Configuration received (Model: {model_name}, Method: {method})"}).encode())
                                except socket.error as send_err:
                                     logger.warning(f"[{addr}] Failed to send config confirmation: {send_err}")

                            except Exception as model_init_e:
                                logger.error(f"[{addr}] Failed to initialize Gemini model '{model_name}': {model_init_e}", exc_info=True) # Log traceback
                                try:
                                    # Provide more specific error if possible
                                    error_msg = f"Failed to initialize model '{model_name}'. Check model name and API key permissions."
                                    conn.sendall(json.dumps({"status": "error", "message": error_msg }).encode())
                                except socket.error: pass
                        else:
                            logger.warning(f"[{addr}] Invalid configuration message: {client_message}")

                    # --- Handle Context Response ---
                    elif msg_type == "context_response":
                        request_id = client_message.get("request_id")
                        received_context = client_message.get("context")
                        logger.debug(f"[{addr}] Received context response for request {request_id}")

                        if request_id in pending_context_requests:
                            pending_data = pending_context_requests.pop(request_id) # Remove as we process
                            script = None
                            method = pending_data['method']
                            req_model_name = pending_data['model_name'] # Get model name from pending data
                            req_conn = pending_data['conn'] # Get the connection associated with the request
                            req_addr = pending_data['addr']

                            if req_conn != conn:
                                logger.warning(f"[{addr}] Mismatched connection for request {request_id}. Original: {req_addr}. Ignoring.")
                                continue

                            connection_config = client_configs.get(req_conn)
                            if not connection_config or not connection_config.get('genai_model_instance'):
                                logger.error(f"[{addr}] Could not find valid Gemini model instance for request {request_id}. Config missing or incomplete.")
                                try:
                                    conn.sendall(json.dumps({
                                        "status": "error",
                                        "message": f"Server configuration error (Request ID: {request_id})",
                                        "request_id": request_id
                                    }).encode())
                                except socket.error: pass
                                continue # Skip processing this request

                            active_genai_model = connection_config['genai_model_instance']
                            logger.debug(f"[{addr}] Using model instance {type(active_genai_model)} for request {request_id}")

                            if method == "gemini":
                                audio_bytes = pending_data.get('audio_bytes')
                                if audio_bytes:
                                    # Pass the specific model instance
                                    script = process_audio_with_gemini(active_genai_model, audio_bytes, req_model_name, received_context)
                                else:
                                    logger.error(f"[{addr}] No audio data found for Gemini request {request_id}")
                            elif method in ["whisper", "google_stt"]:
                                text = pending_data.get('text')
                                if text:
                                    # Pass the specific model instance
                                    script = process_text_with_gemini(active_genai_model, text, req_model_name, received_context)
                                else:
                                     logger.error(f"[{addr}] No transcribed text found for {method} request {request_id}")
                            else:
                                logger.error(f"[{addr}] Unknown method '{method}' in pending request {request_id}")

                            # Send script or error back
                            try:
                                if script:
                                    logger.info(f"[{addr}] Script generated successfully for request {request_id}.")
                                    conn.sendall(json.dumps({
                                        "status": "script",
                                        "message": "Generated script",
                                        "script": script,
                                        "request_id": request_id
                                    }).encode())
                                else:
                                    logger.warning(f"[{addr}] Failed to generate script for request {request_id}.")
                                    conn.sendall(json.dumps({
                                        "status": "error",
                                        "message": f"Failed to generate script (Request ID: {request_id})",
                                        "request_id": request_id
                                    }).encode())
                            except socket.error as send_err:
                                logger.error(f"[{addr}] Failed to send script/error for request {request_id}: {send_err}")

                        else:
                            logger.warning(f"[{addr}] Received context response for unknown/expired request ID: {request_id}")

                    # --- Handle Direct Text Command ---
                    elif msg_type == "process_text":
                        text_to_process = client_message.get("text")
                        context_for_text = client_message.get("context") # Allow context with text input too
                        request_id_text = str(uuid.uuid4()) # Generate ID for tracking

                        connection_config = client_configs.get(conn)
                        if text_to_process and connection_config and connection_config.get('genai_model_instance'):
                            active_genai_model = connection_config['genai_model_instance']
                            text_model_name = connection_config['model_name']
                            logger.info(f"[{addr}] Processing direct text command (ID: {request_id_text})...")
                            script = process_text_with_gemini(active_genai_model, text_to_process, text_model_name, context_for_text)

                            try:
                                if script:
                                    logger.info(f"[{addr}] Script generated successfully for text request {request_id_text}.")
                                    conn.sendall(json.dumps({
                                        "status": "script",
                                        "message": "Generated script from text",
                                        "script": script,
                                        "request_id": request_id_text
                                    }).encode())
                                else:
                                    logger.warning(f"[{addr}] Failed to generate script for text request {request_id_text}.")
                                    conn.sendall(json.dumps({
                                        "status": "error",
                                        "message": f"Failed to generate script from text (Request ID: {request_id_text})",
                                        "request_id": request_id_text
                                    }).encode())
                            except socket.error as send_err:
                                logger.error(f"[{addr}] Failed to send script/error for text request {request_id_text}: {send_err}")

                        else:
                            logger.warning(f"[{addr}] Received invalid 'process_text' request or server not configured: {client_message}")
                            try:
                                conn.sendall(json.dumps({
                                    "status": "error",
                                    "message": "Invalid text command or server not configured.",
                                    "request_id": request_id_text
                                    }).encode())
                            except socket.error: pass

                    # --- Handle Unknown Message Type ---
                    else:
                        logger.warning(f"[{addr}] Received unknown message type: {msg_type}")

                except json.JSONDecodeError:
                    logger.error(f"[{addr}] Failed to decode JSON from client: {client_data}")
                except UnicodeDecodeError:
                     logger.error(f"[{addr}] Failed to decode client data as UTF-8: {client_data}")
                except Exception as msg_proc_err: # Catch broader errors during message processing
                    logger.error(f"[{addr}] Error processing client message: {msg_proc_err}", exc_info=True)

            except socket.timeout:
                continue # Normal timeout
            except socket.error as sock_err:
                logger.error(f"[{addr}] Socket error in message handler: {sock_err}")
                break # Assume connection is lost
            except Exception as e:
                logger.error(f"[{addr}] Unexpected error in message handler loop: {e}", exc_info=True)
                break # Exit loop on unexpected error

    except Exception as thread_err:
        logger.error(f"[{addr}] Error in client message handler thread: {thread_err}", exc_info=True)
    finally:
        logger.info(f"[{addr}] Client message handler thread finished.")
        if conn in client_configs:
            try:
                del client_configs[conn]
                logger.debug(f"[{addr}] Removed config for disconnected client.")
            except KeyError:
                 logger.debug(f"[{addr}] Config already removed for connection on handler exit.")
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except (socket.error, OSError):
            pass # Ignore errors if already closed
        conn.close()


# --- Main Server Function ---
def start_standalone_voice_recognition_server():
    """Starts the standalone voice recognition server."""
    # Check dependencies after imports are attempted
    if not DEPENDENCIES_INSTALLED:
        # Logger might not be fully set up if basic imports failed, print as fallback
        print("CRITICAL: Cannot start server due to missing dependencies. Check logs and run setup.py.", file=sys.stderr)
        return # Exit if core dependencies were missing

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.critical("GEMINI_API_KEY environment variable not found. Cannot start server.")
        sys.exit(1)

    threads = []
    server_socket = None # Define server socket outside try block for finally clause
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow address reuse
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        logger.info(f"Voice recognition server started on {HOST}:{PORT}")
        logger.info("Waiting for Blender to connect...")

        while not stop_server.is_set():
            try:
                server_socket.settimeout(1.0)
                conn, addr = server_socket.accept()
                conn.settimeout(None) # Reset timeout for the connection socket

                logger.info(f"Connected by {addr}")

                handler_thread = threading.Thread(
                    target=client_message_handler_thread,
                    args=(conn, addr, api_key),
                    daemon=True
                )
                handler_thread.start()
                threads.append(handler_thread)

                listener_thread = threading.Thread(
                    target=server_audio_listener_thread,
                    args=(conn, addr),
                    daemon=True
                )
                listener_thread.start()
                threads.append(listener_thread)

            except socket.timeout:
                continue # Normal timeout, check stop_server flag
            except Exception as accept_err:
                if not stop_server.is_set():
                     logger.error(f"Error accepting connection: {accept_err}", exc_info=True)
                break # Exit loop on major accept error

    except OSError as e:
        logger.error(f"Failed to bind to {HOST}:{PORT}. Is the port already in use? Error: {e}")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        logger.info("Server shutting down...")
        stop_server.set() # Signal threads to stop
        if server_socket:
             server_socket.close() # Close the server socket

        join_timeout = 2.0
        # Filter out None or finished threads before joining
        active_threads = [t for t in threads if t is not None and t.is_alive()]
        for t in active_threads:
            try:
                 t.join(timeout=join_timeout)
            except Exception as join_err:
                 logger.warning(f"Error joining thread {t.name}: {join_err}")

        pending_context_requests.clear()
        client_configs.clear()
        logger.info("Server shutdown complete.")


if __name__ == "__main__":
    # Add the diagnostic prints here if needed for debugging startup issues
    # import sys
    # print(f"--- Running with: {sys.executable}")

    logger.info("Starting standalone voice recognition server...")
    try:
        start_standalone_voice_recognition_server()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping server...")
        stop_server.set()
    except Exception as main_err:
         logger.critical(f"Critical error in main execution: {main_err}", exc_info=True)
    finally:
        # Ensure stop signal is set on any exit path
        if not stop_server.is_set():
             stop_server.set()
        # Give threads a moment to potentially see the stop signal before main exits
        time.sleep(0.1)
