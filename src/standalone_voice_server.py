import os
import sys
import time
import json
import socket
import threading
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import dotenv with better error handling
try:
    import dotenv
    # Load environment variables from .env file if it exists
    env_path = Path(__file__).parent.parent / '.env'
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
    print("Required dependencies not installed. Please run setup.py first.")
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

def voice_recognition_thread(conn, api_key, model):
    """Thread function to handle voice recognition"""
    # Initialize the recognizer
    recognizer = sr.Recognizer()
    
    try:
        # Send ready message to Blender
        conn.sendall(json.dumps({"status": "ready", "message": "Voice recognition server ready"}).encode())
        
        # Adjust for ambient noise
        with sr.Microphone() as source:
            conn.sendall(json.dumps({"status": "info", "message": "Adjusting for ambient noise... Please wait."}).encode())
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            conn.sendall(json.dumps({"status": "info", "message": "Ready to listen. Speak your command..."}).encode())
            
            while not stop_server.is_set():
                try:
                    # Listen for audio with a shorter timeout to check stop flag more frequently
                    audio = recognizer.listen(source, timeout=3, phrase_time_limit=10)
                    
                    # Check if we should stop
                    if stop_server.is_set():
                        break
                    
                    conn.sendall(json.dumps({"status": "info", "message": "Processing your command..."}).encode())
                    
                    # Transcribe audio to text
                    text = transcribe_audio(recognizer, audio)
                    
                    if text:
                        conn.sendall(json.dumps({"status": "transcribed", "message": f"Transcribed: {text}"}).encode())
                        
                        # Process with Gemini API
                        script = process_with_gemini(text, api_key, model)
                        
                        if script:
                            conn.sendall(json.dumps({"status": "script", "message": f"Generated script", "script": script}).encode())
                        else:
                            conn.sendall(json.dumps({"status": "error", "message": "Failed to generate script from command."}).encode())
                    else:
                        conn.sendall(json.dumps({"status": "error", "message": "Could not understand audio. Please try again."}).encode())
                            
                except sr.WaitTimeoutError:
                    # This is normal, just continue listening
                    pass
                except Exception as e:
                    conn.sendall(json.dumps({"status": "error", "message": f"Error during listening: {str(e)}"}).encode())
                    break
    except Exception as e:
        conn.sendall(json.dumps({"status": "error", "message": f"Error initializing microphone: {str(e)}"}).encode())
    
    conn.sendall(json.dumps({"status": "stopped", "message": "Voice recognition stopped."}).encode())

def start_server():
    """Start the voice recognition server"""
    # Get API key from environment
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    
    if not api_key:
        print("Please set the GEMINI_API_KEY environment variable.")
        sys.exit(1)
    
    # Create a socket server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        
        print(f"Voice recognition server started on {HOST}:{PORT}")
        print("Waiting for Blender to connect...")
        
        # Set a timeout for accept to allow checking the stop flag
        s.settimeout(1.0)
        
        while not stop_server.is_set():
            try:
                conn, addr = s.accept()
                print(f"Connected by {addr}")
                
                # Start voice recognition in a new thread
                thread = threading.Thread(
                    target=voice_recognition_thread,
                    args=(conn, api_key, model),
                    daemon=True
                )
                thread.start()
                
                # Wait for the thread to finish
                while thread.is_alive() and not stop_server.is_set():
                    time.sleep(0.1)
                    
                # Close the connection when done
                conn.close()
            except socket.timeout:
                # This is expected, just continue the loop
                pass
            except Exception as e:
                print(f"Error in server: {e}")
                break
        
        print("Server shutting down...")

def main():
    """Main function to start the server"""
    print("Starting standalone voice recognition server...")
    
    # Start the server in a separate thread
    server_thread = threading.Thread(target=start_server)
    server_thread.start()
    
    try:
        # Keep the main thread running until Ctrl+C
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        stop_server.set()
        
    # Wait for the server thread to finish
    server_thread.join()
    print("Server stopped.")

if __name__ == "__main__":
    main()