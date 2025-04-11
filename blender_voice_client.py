import os
import sys
import json
import socket
import threading
import subprocess
from pathlib import Path

# Socket client configuration
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

# Flag to signal the client to stop
stop_flag = threading.Event()

# Global variables for connection management
client_socket = None
client_thread = None

def get_python_executable():
    """Get the path to the Python executable in the addon's environment"""
    addon_dir = Path(__file__).parent
    
    # Try the Linux environment first (env_linux)
    if sys.platform != "win32":
        env_dir = addon_dir / "env_linux"
        python_path = env_dir / "bin" / "python"
        if python_path.exists():
            return str(python_path)
    
    # Try the Windows environment (env)
    env_dir = addon_dir / "env"
    
    if sys.platform == "win32":
        python_path = env_dir / "Scripts" / "python.exe"
    else:
        python_path = env_dir / "bin" / "python"
    
    if not python_path.exists():
        raise FileNotFoundError(f"Python environment not found at {env_dir}. Please run setup.py first.")
    
    return str(python_path)

def start_voice_server():
    """Start the standalone voice server as a subprocess"""
    try:
        # Get the path to the standalone server script in src directory
        server_script = Path(__file__).parent / "src" / "standalone_voice_server.py"
        
        # Start the server as a subprocess
        process = subprocess.Popen(
            [get_python_executable(), str(server_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        # Give the server a moment to start up
        import time
        time.sleep(1)
        
        return process
    except Exception as e:
        print(f"Error starting voice server: {e}")
        return None

def connect_to_server(callback=None):
    """Connect to the voice recognition server"""
    global client_socket
    
    try:
        # Create a socket object
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Connect to the server
        client_socket.connect((HOST, PORT))
        
        if callback:
            callback("Connected to voice recognition server")
        
        return True
    except Exception as e:
        if callback:
            callback(f"Error connecting to server: {e}")
        return False

def receive_messages(callback=None):
    """Receive messages from the server"""
    global client_socket
    
    if not client_socket:
        if callback:
            callback("Not connected to server")
        return
    
    while not stop_flag.is_set():
        try:
            # Set a timeout to allow checking the stop flag
            client_socket.settimeout(0.5)
            
            # Receive data from the server
            data = client_socket.recv(4096)
            
            if not data:
                # Connection closed by server
                if callback:
                    callback("Connection closed by server")
                break
            
            # Parse the JSON message
            message = json.loads(data.decode())
            
            # Process the message based on its status
            if message["status"] == "script":
                # Extract the script and add it to the execution queue
                script = message.get("script", "")
                # Strip markdown code block markers if present
                script = script.replace("```python", "").replace("```", "").strip()
                if script and callback:
                    # Print the script to terminal for debugging
                    print(f"\nExecuting script:\n{script}\n")
                    # Pass the entire message to the callback with cleaned script
                    callback({"status": "script", "message": "Received script", "script": script})
            else:
                # For other message types, just pass the message to the callback
                if callback:
                    callback(message["message"])
                    
        except socket.timeout:
            # This is expected, just continue the loop
            pass
        except json.JSONDecodeError as e:
            if callback:
                callback(f"Error decoding message: {e}")
            # Optionally break or continue here depending on desired behavior
        except socket.error as e: # Catch specific socket errors first (more specific than generic Exception)
            if callback:
                callback(f"Socket error receiving message: {e}")
            break # Break loop on socket errors
        # Removed generic Exception catch to isolate potential issues
    
    # Close the socket when done
    if client_socket:
        try:
            client_socket.close()
        except:
            pass
        client_socket = None

def start_client(callback=None):
    """Start the voice recognition client"""
    global client_thread, stop_flag
    
    # If already connected, stop first
    if client_thread and client_thread.is_alive():
        stop_client(callback)
        # Give it a moment to clean up
        import time
        time.sleep(0.5)
    
    # Reset the stop flag - ensure it's always a threading.Event
    # This is critical to prevent 'function' object has no attribute 'clear' error
    stop_flag = threading.Event()
    
    # Start the voice server if it's not already running
    server_process = start_voice_server()
    
    # Connect to the server
    if not connect_to_server(callback):
        if callback:
            callback("Failed to connect to voice recognition server")
        return False
    
    # Create a separate thread for receiving messages
    client_thread = threading.Thread(
        target=receive_messages,
        args=(callback,),
        daemon=True
    )
    client_thread.start()
    
    if callback:
        callback("Voice recognition client started")
    
    return True

def stop_client(callback=None):
    """Stop the voice recognition client"""
    global client_thread, client_socket
    
    # Signal the thread to stop
    stop_flag.set()
    
    # Close the socket
    if client_socket:
        try:
            client_socket.close()
        except:
            pass
        client_socket = None
    
    # Wait for the thread to finish (with timeout)
    if client_thread and client_thread.is_alive():
        client_thread.join(timeout=2.0)
    
    if callback:
        callback("Voice recognition client stopped")
    
    return True

# For testing as standalone script
if __name__ == "__main__":
    def print_callback(message):
        print(f"[CLIENT] {message}")
    
    print("Starting voice recognition client...")
    if start_client(print_callback):
        try:
            # Keep the main thread running until Ctrl+C
            import time
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping client...")
            stop_client(print_callback)
    
    print("Client stopped.")
