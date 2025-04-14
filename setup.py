import os
import os
import sys
import subprocess
import venv
from pathlib import Path
import importlib.util
from urllib.error import URLError

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

        # Attempt to download the Whisper 'small' model
        print("\nAttempting to download Whisper 'small' model (this may take a while)...")
        try:
            # Dynamically import whisper after installation
            spec = importlib.util.spec_from_file_location(
                "whisper", env_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "whisper" / "__init__.py"
            )
            if spec and spec.loader:
                 whisper = importlib.util.module_from_spec(spec)
                 sys.modules["whisper"] = whisper # Add to sys.modules for subsequent imports if needed
                 spec.loader.exec_module(whisper)
                 print("Loading Whisper model...")
                 whisper.load_model("small")
                 print("Whisper 'small' model downloaded/loaded successfully.")
            else:
                 print("Could not dynamically load the whisper library after installation.")
                 raise ImportError("Whisper library spec not found.")

        except (URLError, OSError, ImportError, Exception) as e: # Catch potential download/filesystem/import errors
            print("\n--- Whisper Model Download Failed ---")
            print(f"Error encountered: {e}")
            print("Could not automatically download the Whisper 'small' model.")
            print("This might be due to network issues, firewall restrictions, insufficient disk space, or permissions.")
            print(f"Whisper models are typically stored in: {os.path.expanduser('~/.cache/whisper')}")
            print("Please ensure you have a stable internet connection and write permissions to the cache directory.")
            print("You can try downloading the model manually later by running a Python script with:")
            print("  import whisper")
            print("  whisper.load_model('small')")
            # Don't return False here, setup can continue, but warn the user.

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
