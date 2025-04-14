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
    else:
        python_path = env_dir / "bin" / "python"
        pip_path = env_dir / "bin" / "pip"

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
            "pytest"
        ]

        print("Installing required dependencies...")
        for dep in dependencies:
            try:
                print(f"Installing {dep}...")
                subprocess.check_call([str(python_path), "-m", "pip", "install", dep])
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to install {dep}: {e}")
                continue

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