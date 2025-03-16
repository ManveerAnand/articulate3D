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
            "PyAudio", 
            "google-generativeai", 
            "pytest"
        ]
        
        # Check if LiveKit should be installed
        use_livekit = input("Do you want to enable LiveKit for enhanced real-time audio processing? (y/n): ").lower() == 'y'
        if use_livekit:
            dependencies.append("livekit-server-sdk")
            print("LiveKit support will be enabled.")
        
        # Install required packages
        subprocess.check_call([
            str(pip_path), "install", 
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