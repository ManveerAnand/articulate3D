import os
import os
import os
import sys
import subprocess
import venv
from pathlib import Path

def create_virtual_environment(env_dir):
    """Create a virtual environment for the addon"""
    print(f"Creating virtual environment at {env_dir}...")
    venv.create(env_dir, with_pip=True)
    return True

def install_dependencies(env_dir):
    """Install required dependencies in the virtual environment"""
    # Get the path to the Python executable in the virtual environment
    if sys.platform == "win32":
        python_path = env_dir / "Scripts" / "python.exe"
        pip_path = env_dir / "Scripts" / "pip.exe"
    else:
        python_path = env_dir / "bin" / "python"
        pip_path = env_dir / "bin" / "pip"
    
    if not python_path.exists():
        print(f"Error: Python executable not found at {python_path}")
        return False
    
    print("Installing required dependencies...")
    try:
        # Base dependencies - ensure python-dotenv is installed first to avoid import errors
        dependencies = [
            "python-dotenv",
            "SpeechRecognition",
            "PyAudio", # Keep for now, client might need it
            "google-genai", # Updated SDK
            "openai-whisper", # Added for Whisper
            "google-cloud-speech", # Added for Google Cloud STT
            "sounddevice", # Recommended for client recording
            "numpy", # Often needed with audio/sounddevice
            # "torch", # Removed: No longer needed for Silero VAD
            # "torchaudio", # Removed: No longer needed for Silero VAD
            "pytest"
            # Removed: "webrtcvad"
        ]
        
        # Install required packages using 'python -m pip' for better reliability
        subprocess.check_call([
            str(python_path), "-m", "pip", "install",
            *dependencies
        ])
        
        # Create .env file if it doesn't exist
        env_file = Path(__file__).parent / ".env"
        env_example = Path(__file__).parent / ".env.example"
        
        if not env_file.exists() and env_example.exists():
            print("\nCreating .env file from template...")
            with open(env_example, 'r') as example, open(env_file, 'w') as env:
                env.write(example.read())
            print(".env file created. Please edit it to add your API keys.")

        print("Dependencies installed successfully!")

        # Run whisper_test.py to trigger model download
        whisper_test_script = Path(__file__).parent / "whisper_test.py"
        if whisper_test_script.exists():
            print("\nRunning Whisper test script to download/verify the 'small' model...")
            print("(This may take a moment and requires microphone access)...")
            try:
                # Use subprocess.run for better control and error checking
                result = subprocess.run(
                    [str(python_path), str(whisper_test_script)],
                    check=True, # Raise CalledProcessError on failure
                    capture_output=True, # Capture stdout/stderr
                    text=True, # Decode output as text
                    cwd=Path(__file__).parent # Run from the addon directory
                )
                print("Whisper test script ran successfully.")
                # Optionally print stdout/stderr if needed for debugging, but can be verbose
                # print("Whisper Test Output:\n", result.stdout)
                # if result.stderr:
                #     print("Whisper Test Errors:\n", result.stderr)

            except subprocess.CalledProcessError as e:
                print("\n--- Whisper Test Script Failed ---")
                print(f"Error running whisper_test.py: {e}")
                print("The Whisper 'small' model might not have been downloaded correctly.")
                print("Please check the output above for errors from the script.")
                print("You may need to run 'python whisper_test.py' manually to diagnose.")
                print("Common issues include missing ffmpeg, microphone access problems, or network errors during download.")
                # Continue setup, but warn the user
            except FileNotFoundError:
                 print(f"\nError: Could not find whisper_test.py at {whisper_test_script}")

        else:
            print(f"\nWarning: whisper_test.py not found at {whisper_test_script}. Skipping model download check.")


        print("\nNote: If using the Whisper method, ensure ffmpeg is installed on your system.")
        print("(e.g., 'sudo apt install ffmpeg' or 'brew install ffmpeg' or 'choco install ffmpeg')")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False

def setup():
    """Set up the Articulate 3D addon"""
    # Get the addon directory
    addon_dir = Path(__file__).parent
    
    # Create appropriate environment based on platform
    if sys.platform == "win32":
        env_dir = addon_dir / "env"
    else:
        env_dir = addon_dir / "env_linux"
    
    # Create virtual environment if it doesn't exist
    if not env_dir.exists():
        if not create_virtual_environment(env_dir):
            print("Failed to create virtual environment.")
            return False
    
    # Install dependencies
    if not install_dependencies(env_dir):
        print("Failed to install dependencies.")
        return False
    
    print("\nSetup completed successfully!")
    print("\nTo use the Articulate 3D addon:")
    print("1. Open Blender")
    print("2. Go to Edit > Preferences > Add-ons")
    print("3. Click 'Install' and select the addon directory")
    print("4. Enable the 'Articulate 3D' addon")
    print("5. Access the addon from the 3D View sidebar under 'Voice' tab")
    
    return True

if __name__ == "__main__":
    print("=== Articulate 3D Setup ===\n")
    setup()
