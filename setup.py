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
        # Install PyTorch CPU-only first
        print("Installing PyTorch (CPU version)...")
        subprocess.check_call([
            str(python_path), "-m", "pip", "install",
            "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu"
        ])

        # Read requirements from requirements.txt
        print("Reading dependencies from requirements.txt...")
        requirements_path = Path(__file__).parent / "requirements.txt"
        dependencies = []
        if requirements_path.exists():
            try:
                with open(requirements_path, 'r', encoding='utf-8-sig') as f: # Use utf-8-sig to handle potential BOM
                    # Filter out comments, empty lines, and PyTorch/Torchaudio (installed separately)
                    dependencies = [
                        line.strip() for line in f
                        if line.strip() and not line.startswith('#') and 'torch' not in line.lower()
                    ]
                print(f"Found {len(dependencies)} dependencies in requirements.txt (excluding torch).")
            except Exception as e:
                print(f"Error reading requirements.txt: {e}")
                # Decide if we should stop or continue with an empty list
                # For now, let's print the error and continue with potentially empty list
        else:
            print(f"Warning: {requirements_path} not found. Cannot install dependencies from file.")
            # Fallback to empty list or define essential defaults? Let's use empty for now.

        # Install required packages using 'python -m pip' for better reliability
        if dependencies: # Only run if we found dependencies
            print("Installing dependencies from requirements.txt...")
            subprocess.check_call([
                str(python_path), "-m", "pip", "install",
                *dependencies
            ])
        else:
            print("No dependencies found in requirements.txt to install (excluding torch).")

        # Create .env file if it doesn't exist
        env_file = Path(__file__).parent / ".env"
        env_example = Path(__file__).parent / ".env.example"
        
        if not env_file.exists() and env_example.exists():
            print("\nCreating .env file from template...")
            with open(env_example, 'r') as example, open(env_file, 'w') as env:
                env.write(example.read())
            print(".env file created. Please edit it to add your API keys.")
        
        print("Dependencies installed successfully!")
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
