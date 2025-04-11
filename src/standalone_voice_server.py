import os
import sys
import time
import json
import socket
import threading
import logging # Import logging
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Logging Setup ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_file = Path(__file__).parent.parent / 'articulate3d_server.log' # Log file in project root

# Configure root logger for console output
logging.basicConfig(level=logging.INFO, format=log_format, handlers=[logging.StreamHandler(sys.stdout)])

# Create a specific logger for this module
logger = logging.getLogger(__name__) # Use __name__ for logger name
logger.setLevel(logging.INFO) # Ensure logger level is set

# Add file handler
try:
    file_handler = logging.FileHandler(log_file, mode='a') # Use append mode
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)
    logger.info(f"--- Log session started. Logging to {log_file} ---")
except Exception as e:
    logging.error(f"Failed to set up file logging to {log_file}: {e}") # Use root logger if specific logger fails

# --- End Logging Setup ---


# Try to import dotenv with better error handling
try:
    import dotenv
    # Load environment variables from .env file if it exists
    # Go two levels up from src/standalone_voice_server.py to find .env in the project root
    project_root = Path(__file__).parent.parent
    env_path = project_root / '.env'
    if env_path.exists():
        logger.info(f"Loading environment variables from {env_path}")
        dotenv.load_dotenv(env_path)
    else:
        logger.info(".env file not found, relying on system environment variables.")
except ImportError:
    # Use logger for warnings
    logger.warning("python-dotenv module not found. Environment variables will not be loaded from .env file.")
    logger.warning("Please run setup.py to install required dependencies.")

# Import speech recognition libraries
try:
    import speech_recognition as sr
    import google.generativeai as genai
    DEPENDENCIES_INSTALLED = True
except ImportError:
    DEPENDENCIES_INSTALLED = False
    # Use logger for critical errors before exiting
    logger.critical("Required dependencies (SpeechRecognition/google-generativeai) not installed. Please run setup.py first.")
    sys.exit(1)


# Socket server configuration
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

# Flag to signal the server to stop
stop_server = threading.Event()

def transcribe_audio(recognizer, audio):
    """Transcribe audio to text using Google Speech Recognition"""
    # Check if a custom speech API key is provided
    speech_api_key = os.environ.get("SPEECH_API_KEY", None)
    
    try:
        # Use Google Speech Recognition with API key if provided
        if speech_api_key:
            logger.debug("Using Google Speech Recognition with provided API key.")
            text = recognizer.recognize_google(audio, key=speech_api_key)
        else:
            # Use free tier if no API key
            logger.debug("Using Google Speech Recognition free tier.")
            text = recognizer.recognize_google(audio)
            
        logger.info(f"Transcribed: {text}")
        return text
    except sr.UnknownValueError:
        logger.warning("Speech Recognition could not understand audio")
        return None
    except sr.RequestError as e:
        logger.error(f"Could not request results from Speech Recognition service; {e}")
        # Try offline fallback if available
        try:
            logger.info("Attempting Sphinx offline fallback...")
            # This requires additional setup and may not work in all environments
            text = recognizer.recognize_sphinx(audio)
            logger.info(f"Offline fallback transcription: {text}")
            return text
        except Exception as sphinx_error:
            logger.error(f"Sphinx offline fallback failed: {sphinx_error}")
            return None

def process_with_gemini(text, api_key, model):
    """Process transcribed text with Gemini API"""
    try:
        logger.debug(f"Configuring Gemini API with model: {model}")
        # Configure the Gemini API
        genai.configure(api_key=api_key)
        
        # Set up the model
        generation_config = {
            "temperature": 0.2,
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        
        # Initialize the model
        model_instance = genai.GenerativeModel(
            model_name=model,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Create the prompt
        prompt = f"""
        You are an assistant that converts voice commands into Blender Python scripts.
        Convert the following voice command into a valid Blender Python script:
        
        Command: {text}
        
        Respond ONLY with the Python script, no explanations or comments.
        The script should be valid Blender Python API code that can be executed directly.
        """
        logger.debug("Sending prompt to Gemini...")
        # Generate the response
        response = model_instance.generate_content(prompt)
        
        # Extract the script from the response
        script = response.text.strip()
        logger.info("Received script from Gemini.")
        logger.debug(f"Generated Script Snippet: {script[:100]}...") # Log snippet
        
        return script
    except Exception as e:
        logger.error(f"Error processing with Gemini: {e}", exc_info=True) # Log traceback
        return None

def voice_recognition_thread(conn, api_key, model):
    """Thread function to handle voice recognition"""
    # Initialize the recognizer
    logger.info("Voice recognition thread started.")
    recognizer = sr.Recognizer()
    
    try:
        # Send ready message to Blender
        logger.debug("Sending 'ready' status to client.")
        conn.sendall(json.dumps({"status": "ready", "message": "Voice recognition server ready"}).encode())
        
        # Adjust for ambient noise
        with sr.Microphone() as source:
            logger.info("Adjusting for ambient noise...")
            conn.sendall(json.dumps({"status": "info", "message": "Adjusting for ambient noise... Please wait."}).encode())
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            logger.info("Ready to listen.")
            conn.sendall(json.dumps({"status": "info", "message": "Ready to listen. Speak your command..."}).encode())
            
            while not stop_server.is_set():
                try:
                    logger.debug("Listening for audio...")
                    # Listen for audio with a shorter timeout to check stop flag more frequently
                    audio = recognizer.listen(source, timeout=3, phrase_time_limit=10)
                    
                    # Check if we should stop
                    if stop_server.is_set():
                        logger.info("Stop flag set, exiting listening loop.")
                        break
                    
                    logger.info("Audio received, processing...")
                    conn.sendall(json.dumps({"status": "info", "message": "Processing your command..."}).encode())
                    
                    # Transcribe audio to text
                    text = transcribe_audio(recognizer, audio)
                    
                    if text:
                        conn.sendall(json.dumps({"status": "transcribed", "message": f"Transcribed: {text}"}).encode())
                        
                        # Process with Gemini API
                        script = process_with_gemini(text, api_key, model)
                        
                        if script:
                            logger.info("Script generated successfully.")
                            conn.sendall(json.dumps({"status": "script", "message": f"Generated script", "script": script}).encode())
                        else:
                            logger.warning("Failed to generate script from command.")
                            conn.sendall(json.dumps({"status": "error", "message": "Failed to generate script from command."}).encode())
                    else:
                        logger.warning("Audio transcription failed.")
                        conn.sendall(json.dumps({"status": "error", "message": "Could not understand audio. Please try again."}).encode())
                            
                except sr.WaitTimeoutError:
                    # This is normal, just continue listening without logging spam
                    logger.debug("Listen timeout, continuing...")
                    pass
                except Exception as e:
                    error_msg = f"Error during listening loop: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    try:
                        conn.sendall(json.dumps({"status": "error", "message": error_msg}).encode())
                    except Exception as send_err:
                        logger.error(f"Failed to send error to client: {send_err}")
                    break # Exit loop on error
    except sr.RequestError as e:
        # Handle errors connecting to speech recognition service specifically
        error_msg = f"Speech Recognition API request failed: {e}"
        logger.error(error_msg)
        try:
            conn.sendall(json.dumps({"status": "error", "message": error_msg}).encode())
        except Exception as send_err:
            logger.error(f"Failed to send error to client: {send_err}")
    except Exception as e:
        # Catch other potential errors during setup (e.g., microphone access)
        error_msg = f"Error initializing microphone or recognizer: {str(e)}"
        logger.error(error_msg, exc_info=True)
        try:
            conn.sendall(json.dumps({"status": "error", "message": error_msg}).encode())
        except Exception as send_err:
            logger.error(f"Failed to send error to client: {send_err}")
    
    # Ensure stopped message is sent even if errors occurred
    try:
        logger.info("Sending 'stopped' status to client.")
        conn.sendall(json.dumps({"status": "stopped", "message": "Voice recognition stopped."}).encode())
    except Exception as send_err:
         logger.error(f"Failed to send stopped message to client: {send_err}")
    logger.info("Voice recognition thread finished.")


def start_server():
    """Start the voice recognition server"""
    # Get API key from environment
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash") # Defaulting to 1.5 flash as per .env.example
    
    if not api_key:
        logger.critical("GEMINI_API_KEY environment variable not set.")
        sys.exit(1)
    
    # Create a socket server
    server_socket = None # Initialize
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        
        logger.info(f"Voice recognition server started on {HOST}:{PORT}")
        logger.info("Waiting for Blender to connect...")
        
        # Set a timeout for accept to allow checking the stop flag
        server_socket.settimeout(1.0)
        
        while not stop_server.is_set():
            conn = None # Initialize conn
            try:
                conn, addr = server_socket.accept()
                logger.info(f"Connected by {addr}")
                
                # Start voice recognition in a new thread
                thread = threading.Thread(
                    target=voice_recognition_thread,
                    args=(conn, api_key, model),
                    daemon=True
                )
                thread.start()
                
                # Wait for the thread to finish (or stop_server signal)
                while thread.is_alive() and not stop_server.is_set():
                    time.sleep(0.1)
                    
                # If thread finished normally, close connection
                if thread.is_alive():
                     logger.warning("Voice recognition thread still alive after loop exit? Forcing stop.")
                     # Potentially signal thread more forcefully if needed, but rely on stop_server for now
                else:
                     logger.info("Voice recognition thread completed.")

                # Close the connection for this client
                if conn:
                    logger.info(f"Closing connection from {addr}")
                    conn.close()
                    conn = None # Reset conn

            except socket.timeout:
                # This is expected, just continue the loop
                logger.debug("Server accept timeout, checking stop flag...")
                pass
            except socket.error as e:
                 logger.error(f"Socket error in server accept loop: {e}", exc_info=True)
                 # Decide if we should break or continue depending on the error
                 # For now, let's break on socket errors in the main loop
                 if conn: conn.close() # Ensure connection is closed on error
                 break
            except Exception as e:
                logger.error(f"Unexpected error in server accept loop: {e}", exc_info=True)
                if conn: conn.close() # Ensure connection is closed on error
                break # Break on unexpected errors
        
    except Exception as e:
         logger.critical(f"Failed to start server: {e}", exc_info=True)
    finally:
        if server_socket:
            server_socket.close()
            logger.info("Server socket closed.")
        logger.info("Server shutting down...")


def main():
    """Main function to start the server"""
    logger.info("Starting standalone voice recognition server...")
    
    # Start the server in a separate thread
    server_thread = threading.Thread(target=start_server)
    server_thread.start()
    
    try:
        # Keep the main thread running until Ctrl+C
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("\nCtrl+C detected. Shutting down server...")
        stop_server.set()
        
    # Wait for the server thread to finish
    server_thread.join()
    logger.info("Server stopped.")

if __name__ == "__main__":
    main()
