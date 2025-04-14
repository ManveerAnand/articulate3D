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
    if sys.platform == "win32":
        python_path = env_dir / "Scripts" / "python.exe"
        pip_path = env_dir / "Scripts" / "pip.exe"
        activate_script = env_dir / "Scripts" / "activate.bat"
    else:
        python_path = env_dir / "bin" / "python"
        pip_path = env_dir / "bin" / "pip"
        activate_script = env_dir / "bin" / "activate"

    if not python_path.exists():
        print(f"Error: Python executable not found at {python_path}")
        return False

    try:
        print("Upgrading pip, setuptools, and wheel...")
        subprocess.check_call([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

        # Install dependencies one by one
        dependencies = [
            "python-dotenv",
            "SpeechRecognition",
            "PyAudio",
            "google-genai",
            "git+https://github.com/openai/whisper.git",  # Install directly from GitHub
            "google-cloud-speech",
            "sounddevice",
            "numpy",
            "pytest",
            "ffmpeg-python"  # Added ffmpeg-python for audio processing
        ]

        print("Installing required dependencies...")
        for dep in dependencies:
            try:
                print(f"Installing {dep}...")
                subprocess.check_call([str(python_path), "-m", "pip", "install", dep])
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to install {dep}: {e}")
                continue

        # Special handling for vosk
        print("\nInstalling vosk...")
        try:
            # First try installing from PyPI
            subprocess.check_call([str(python_path), "-m", "pip", "install", "vosk"])
        except subprocess.CalledProcessError:
            print("Failed to install vosk from PyPI, trying alternative methods...")
            try:
                # Try installing from GitHub
                subprocess.check_call([str(python_path), "-m", "pip", "install", "git+https://github.com/alphacep/vosk-api.git"])
            except subprocess.CalledProcessError:
                print("Failed to install vosk from GitHub, trying pre-built wheel...")
                try:
                    # Try installing pre-built wheel for Windows
                    if sys.platform == "win32":
                        subprocess.check_call([str(python_path), "-m", "pip", "install", "https://github.com/alphacep/vosk-api/releases/download/v0.3.45/vosk-0.3.45-cp39-cp39-win_amd64.whl"])
                except subprocess.CalledProcessError:
                    print("Failed to install vosk. Some speech recognition features may not work.")

        # Download Vosk model files
        print("\nDownloading Vosk model files...")
        model_dir = Path(_file_).parent / "models" / "vosk-model-small-en-us"
        if not model_dir.exists():
            model_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                import urllib.request
                import zipfile
                print("Downloading small English model...")
                model_url = "https://alphacep.cn/vosk/models/vosk-model-small-en-us-0.15.zip"
                model_zip = model_dir.parent / "vosk-model-small-en-us-0.15.zip"
                urllib.request.urlretrieve(model_url, model_zip)
                with zipfile.ZipFile(model_zip, 'r') as zip_ref:
                    zip_ref.extractall(model_dir.parent)
                model_zip.unlink()  # Remove the zip file after extraction
                print("Vosk model files downloaded successfully.")
            except Exception as e:
                print(f"Failed to download Vosk model files: {e}")
                print("You can manually download the model from: https://alphacep.cn/vosk/models/")

        env_file = Path(_file_).parent / ".env"
        env_example = Path(_file_).parent / ".env.example"
        if not env_file.exists() and env_example.exists():
            print("\nCreating .env file from template...")
            with open(env_example, 'r') as example, open(env_file, 'w') as env:
                env.write(example.read())
            print(".env file created. Please edit it to add your API keys.")

        whisper_test_script = Path(_file_).parent / "whisper_test.py"
        if whisper_test_script.exists():
            print("\nRunning Whisper test script to download/verify the 'small' model...")
            try:
                result = subprocess.run(
                    [str(python_path), str(whisper_test_script)],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=Path(_file_).parent
                )
                print("Whisper test script ran successfully.")
            except subprocess.CalledProcessError as e:
                print("\n--- Whisper Test Script Failed ---")
                print(f"Error running whisper_test.py: {e}")
            except FileNotFoundError:
                print(f"\nError: Could not find whisper_test.py at {whisper_test_script}")
        else:
            print(f"\nWarning: whisper_test.py not found at {whisper_test_script}. Skipping model download check.")

        print("\nNote: If using the Whisper method, ensure ffmpeg is installed on your system.")
        print("You can install ffmpeg using: https://ffmpeg.org/download.html")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False

def setup():
    """Set up the Articulate 3D addon"""
    addon_dir = Path(_file_).parent
    env_dir = addon_dir / "env" if sys.platform == "win32" else addon_dir / "env_linux"

    if not env_dir.exists():
        if not create_virtual_environment(env_dir):
            print("Failed to create virtual environment.")
            return False

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

if _name_ == "_main_":
    print("=== Articulate 3D Setup ===\n")
    setup()