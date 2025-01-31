import subprocess
import sys
import os
from pathlib import Path

def get_python_executable():
    """Get the path to the Python executable in the addon's environment"""
    addon_dir = Path(__file__).parent
    env_dir = addon_dir / "env"
    
    if sys.platform == "win32":
        python_path = env_dir / "Scripts" / "python.exe"
    else:
        python_path = env_dir / "bin" / "python"
    
    if not python_path.exists():
        raise FileNotFoundError(f"Python environment not found at {python_path}. Please run setup.py first.")
    
    return str(python_path)

def start_listening(api_key=None, model=None, callback=None):
    """Start the voice recognition process"""
    addon_dir = Path(__file__).parent
    script_path = addon_dir / "voice_processor.py"
    
    if not script_path.exists():
        raise FileNotFoundError(f"Voice processor script not found at {script_path}")
    
    python_exe = get_python_executable()
    
    # Pass API key and model as environment variables
    env = os.environ.copy()
    env['GEMINI_API_KEY'] = api_key or ""
    env['GEMINI_MODEL'] = model or "gemini-2.0-flash"
    
    try:
        # Start the voice processor in a separate process
        process = subprocess.Popen(
            [python_exe, str(script_path)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read output in real-time
        while True:
            output = process.stdout.readline()
            if output:
                if callback:
                    callback(output.strip())
                else:
                    print(output.strip())
            
            # Check if process has finished
            if process.poll() is not None:
                break
                
    except Exception as e:
        if callback:
            callback(f"Error: {str(e)}")
        raise 