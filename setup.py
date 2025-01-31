import subprocess
import sys
import venv
from pathlib import Path

def setup_environment():
    addon_dir = Path(__file__).parent
    env_dir = addon_dir / "env"
    
    # Create virtual environment
    venv.create(env_dir, with_pip=True)
    
    # Get pip path
    if sys.platform == "win32":
        pip_path = env_dir / "Scripts" / "pip.exe"
    else:
        pip_path = env_dir / "bin" / "pip"
    
    # Install required packages
    subprocess.check_call([str(pip_path), "install", "SpeechRecognition"])
    subprocess.check_call([str(pip_path), "install", "requests"])
    subprocess.check_call([str(pip_path), "install", "PyAudio"])

if __name__ == "__main__":
    setup_environment() 