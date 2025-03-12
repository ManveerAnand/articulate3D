import os
import sys
import subprocess
import threading
import time
import json
import tempfile
import queue
from pathlib import Path

# Try to import dotenv with better error handling
try:
    import dotenv
    # Load environment variables from .env file if it exists
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        dotenv.load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv module not found. Environment variables will not be loaded from .env file.")
    print("Please run setup.py to install required dependencies.")

# Import speech recognition libraries
try:
    import speech_recognition as sr
    import google.generativeai as genai
    DEPENDENCIES_INSTALLED = True
except ImportError:
    DEPENDENCIES_INSTALLED = False

# Flag to determine if we should use LiveKit (if available)
USE_LIVEKIT = os.environ.get("USE_LIVEKIT", "False").lower() == "true"

# Queue for communication between processes
command_queue = queue.Queue()

# Global variable to track the listening thread
listening_thread = None
# Flag to signal the listening thread to stop
stop_listening_flag = threading.Event()

def get_python_executable():
    """Get the path to the Python executable in the addon's environment"""
    addon_dir = Path(__file__).parent
    env_dir = addon_dir / "env"
    
    if sys.platform == "win32":
        python_path = env_dir / "Scripts" / "python.exe"
    else:
        python_path = env_dir / "bin" / "python"
    
    if not python_path.exists():
        raise FileNotFoundError(f"Python environment not found at {env_dir}. Please run setup.py first.")
    
    return str(python_path)

def check_dependencies():
    """Check if required dependencies are installed"""
    if not DEPENDENCIES_INSTALLED:
        print("Installing required dependencies...")
        try:
            # Base dependencies
            dependencies = [
                "SpeechRecognition", "PyAudio", "google-generativeai", "python-dotenv"
            ]
            
            # Add LiveKit if enabled
            if USE_LIVEKIT:
                dependencies.append("livekit-server-sdk")
                
            subprocess.check_call([
                get_python_executable(),
                "-m", "pip", "install", 
                *dependencies
            ])
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing dependencies: {e}")
            return False
    return True

def transcribe_audio(recognizer, audio):
    """Transcribe audio to text using Google Speech Recognition"""
    # Check if a custom speech API key is provided
    speech_api_key = os.environ.get("SPEECH_API_KEY", None)
    
    try:
        # Use Google Speech Recognition with API key if provided
        if speech_api_key:
            text = recognizer.recognize_google(audio, key=speech_api_key)
        else:
            # Use free tier if no API key
            text = recognizer.recognize_google(audio)
            
        print(f"Transcribed: {text}")
        return text
    except sr.UnknownValueError:
        print("Speech Recognition could not understand audio")
        return None
    except sr.RequestError as e:
        print(f"Could not request results from Speech Recognition service; {e}")
        # Try offline fallback if available
        try:
            # This requires additional setup and may not work in all environments
            text = recognizer.recognize_sphinx(audio)
            print(f"Offline fallback transcription: {text}")
            return text
        except:
            return None

def process_with_gemini(text, api_key, model):
    """Process transcribed text with Gemini API"""
    try:
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
        
        # Generate the response
        response = model_instance.generate_content(prompt)
        
        # Extract the script from the response
        script = response.text.strip()
        
        return script
    except Exception as e:
        print(f"Error processing with Gemini: {e}")
        return None

def listen_for_commands(api_key, model, callback=None):
    """Listen for voice commands and process them"""
    if not check_dependencies():
        if callback:
            callback("Failed to install required dependencies. Please install manually.")
        return
    
    # Initialize the recognizer
    recognizer = sr.Recognizer()
    
    try:
        # Adjust for ambient noise
        with sr.Microphone() as source:
            if callback:
                callback("Adjusting for ambient noise... Please wait.")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            if callback:
                callback("Ready to listen. Speak your command...")
            
            # Reset the stop flag before starting
            stop_listening_flag.clear()
            
            while not stop_listening_flag.is_set():
                try:
                    # Listen for audio with a shorter timeout to check stop flag more frequently
                    audio = recognizer.listen(source, timeout=3, phrase_time_limit=10)
                    
                    # Check if we should stop
                    if stop_listening_flag.is_set():
                        break
                    
                    if callback:
                        callback("Processing your command...")
                    
                    # Transcribe audio to text
                    text = transcribe_audio(recognizer, audio)
                    
                    if text:
                        if callback:
                            callback(f"Transcribed: {text}")
                        
                        # Process with Gemini API
                        script = process_with_gemini(text, api_key, model)
                        
                        if script:
                            if callback:
                                callback(f"Generated script:\n{script}")
                            
                            # Add to command queue for execution
                            command_queue.put(script)
                        else:
                            if callback:
                                callback("Failed to generate script from command.")
                    else:
                        if callback:
                            callback("Could not understand audio. Please try again.")
                            
                except sr.WaitTimeoutError:
                    # This is normal, just continue listening
                    pass
                except Exception as e:
                    if callback:
                        callback(f"Error during listening: {str(e)}")
                    break
    except Exception as e:
        if callback:
            callback(f"Error initializing microphone: {str(e)}")
    
    if callback:
        callback("Voice recognition stopped.")
    return

def start_listening(api_key=None, model="gemini-2.0-flash", callback=None):
    """Start the voice recognition process"""
    global listening_thread
    
    # If already listening, stop first
    if listening_thread and listening_thread.is_alive():
        stop_listening(callback)
        # Give it a moment to clean up
        time.sleep(0.5)
    
    # Reset the stop flag
    stop_listening_flag.clear()
    
    # Create a separate thread for listening
    listening_thread = threading.Thread(
        target=listen_for_commands,
        args=(api_key, model, callback),
        daemon=True
    )
    listening_thread.start()
    
    if callback:
        callback("Voice recognition started in background.")
    
    return listening_thread

def stop_listening(callback=None):
    """Stop the voice recognition process"""
    global listening_thread
    
    if listening_thread and listening_thread.is_alive():
        # Signal the thread to stop
        stop_listening_flag.set()
        
        # Wait for the thread to finish (with timeout)
        listening_thread.join(timeout=2.0)
        
        if callback:
            callback("Voice recognition stopped.")
        
        return True
    else:
        if callback:
            callback("No voice recognition running.")
        return False

def get_next_command():
    """Get the next command from the queue if available"""
    try:
        return command_queue.get_nowait()
    except queue.Empty:
        return None

# For testing as standalone script
if __name__ == "__main__":
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    
    if not api_key:
        print("Please set the GEMINI_API_KEY environment variable.")
        sys.exit(1)
    
    print("Starting voice recognition...")
    thread = start_listening(api_key, model, print)
    
    try:
        while True:
            command = get_next_command()
            if command:
                print(f"\nExecuting command:\n{command}\n")
                # In standalone mode, just print the command
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)