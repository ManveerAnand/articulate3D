import os
import sys
import json
import socket
import threading
import subprocess
from pathlib import Path
import bpy # Import bpy for context gathering
import logging # Import logging for the warning in receive_messages

# Socket client configuration
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

# Flag to signal the client to stop
stop_flag = threading.Event()

# Global variables for connection management
client_socket = None
client_thread = None
socket_lock = threading.Lock() # Global lock for socket access

# --- Context Gathering ---
def get_blender_context():
    """Gathers relevant context from Blender's current state."""
    context_data = {
        "mode": "UNKNOWN",
        "scene_name": None,
        "active_object": None, # Will be a dict if active
        "selected_objects": [], # Will be a list of dicts
        "scene_objects": [] # List of names in the main collection
    }
    try:
        if bpy.context and bpy.context.scene:
            context_data["mode"] = bpy.context.mode
            context_data["scene_name"] = bpy.context.scene.name

            # Get active object details safely
            active_obj = getattr(bpy.context, 'active_object', None) # Use getattr
            if active_obj:
                context_data["active_object"] = {
                    "name": active_obj.name,
                    "type": active_obj.type,
                    "location": tuple(active_obj.location),
                    "rotation_euler": tuple(active_obj.rotation_euler),
                    "scale": tuple(active_obj.scale)
                }

            # Get selected objects details safely
            selected_objs = getattr(bpy.context, 'selected_objects', []) # Use getattr
            if selected_objs:
                context_data["selected_objects"] = [
                    {"name": obj.name, "type": obj.type}
                    for obj in selected_objs
                ]

            # Get names of objects in the scene's main collection
            if bpy.context.scene.collection and bpy.context.scene.collection.objects:
                 context_data["scene_objects"] = [obj.name for obj in bpy.context.scene.collection.objects]

    except Exception as e:
        # Removed problematic operator call from except block
        print(f"Error getting Blender context: {e}") # Keep print for console
        # Optionally report to Blender's info area:
        # bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=f"Context Error: {e}"), title="Articulate3D Error", icon='ERROR')

    return context_data
# --- End Context Gathering ---

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
    global client_socket, socket_lock
    
    with socket_lock: # Acquire lock before modifying global socket
        try:
            # Create a socket object
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            print("[DEBUG] connect_to_server: Socket created.") # Log creation
            
            # Connect to the server
            temp_socket.connect((HOST, PORT))
            print("[DEBUG] connect_to_server: Socket connected successfully.") # Log success
            
            client_socket = temp_socket # Assign to global variable *after* successful connection
            
            if callback:
                callback("Connected to voice recognition server")
            
            return True
        except Exception as e:
            print(f"[DEBUG] connect_to_server: Connection failed: {e}") # Log failure
            client_socket = None # Ensure socket is None on failure
            if callback:
                callback(f"Error connecting to server: {e}")
            return False

def receive_messages(callback=None):
    """Receive messages from the server"""
    global client_socket, socket_lock
    print("[DEBUG] receive_messages: Thread started.") # Log thread start
    
    # Check initial socket state under lock
    with socket_lock:
        initial_socket = client_socket
    
    if not initial_socket:
        print("WARNING: receive_messages thread started but client_socket is None. Exiting.")
        if callback:
            callback("Error: receive thread started without connection.")
        return
    
    while not stop_flag.is_set():
        # Capture socket reference locally for this iteration *without* holding lock long term
        sock = None
        with socket_lock:
             sock = client_socket

        if not sock:
            print("WARNING: receive_messages loop detected client_socket is None. Breaking loop.")
            break
            
        try:
            # Set a timeout to allow checking the stop flag
            # print("[DEBUG] receive_messages: Setting timeout...") # Can be noisy
            sock.settimeout(0.5) # Use local variable 'sock'
            
            # Receive data from the server
            # print("[DEBUG] receive_messages: Attempting recv...") # Can be noisy
            data = sock.recv(4096) # Use local variable 'sock'
            # print(f"[DEBUG] receive_messages: recv returned {len(data)} bytes.") # Can be noisy
            
            if not data:
                # Connection closed by server
                print("[DEBUG] receive_messages: recv returned empty, breaking loop.")
                if callback:
                    callback("Connection closed by server")
                break
            
            # Parse the JSON message
            # print("[DEBUG] receive_messages: Decoding JSON...") # Can be noisy
            message = json.loads(data.decode())
            # print(f"[DEBUG] receive_messages: Decoded message: {message}") # Can be noisy
            
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
                # For other message types, pass the full message dictionary
                if callback:
                    callback(message) # <--- Change this line

        except socket.timeout:
            # This is expected, just continue the loop
            pass
        except json.JSONDecodeError as e:
            print(f"[DEBUG] receive_messages: JSONDecodeError: {e}")
            if callback:
                callback(f"Error decoding message: {e}")
            # Optionally break or continue here depending on desired behavior
        except socket.error as e: # Catch specific socket errors first (more specific than generic Exception)
            print(f"[DEBUG] receive_messages: Socket error: {e}. Breaking loop.")
            if callback:
                callback(f"Socket error receiving message: {e}")
            break # Break loop on socket errors
        # Removed generic Exception catch to isolate potential issues
    
    # Cleanup: Close the socket and set global to None under lock
    with socket_lock:
        if client_socket: # Check again in case it was set to None elsewhere
            try:
                print("[DEBUG] receive_messages: Closing socket in cleanup.")
                client_socket.close()
            except Exception as e_close:
                 print(f"Warning: Error closing socket in receive_messages cleanup: {e_close}")
            finally:
                 client_socket = None
                 print("[DEBUG] receive_messages: Global client_socket set to None in cleanup.")
        else:
            print("[DEBUG] receive_messages: client_socket was already None during cleanup.")
            
    print("[DEBUG] receive_messages: Thread finished.") # Log thread end

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
        daemon=True,
        name="ReceiveMessagesThread" # Give the thread a name
    )
    client_thread.start()
    
    if callback:
        callback("Voice recognition client started")
    
    return True

def stop_client(callback=None):
    """Stop the voice recognition client"""
    global client_thread, client_socket, socket_lock
    
    # Signal the thread to stop
    stop_flag.set()
    print("[DEBUG] stop_client: stop_flag set.")
    
    # Explicitly try to close the socket here and set to None immediately
    # Use lock to prevent race conditions
    with socket_lock:
        socket_to_close = client_socket # Capture current socket state
        if socket_to_close:
            print(f"[DEBUG] stop_client: Attempting to close socket {socket_to_close}")
            try:
                # Shutdown might fail if already closed, ignore errors
                socket_to_close.shutdown(socket.SHUT_RDWR)
                print("[DEBUG] stop_client: Socket shutdown attempted.")
            except socket.error as e_shut:
                 # Ignore specific errors indicating already closed/not connected
                 if e_shut.errno not in [10057, 10022, 10054]: # Added 10054 (Connection reset by peer)
                     print(f"Warning: Socket shutdown error in stop_client (errno {e_shut.errno}): {e_shut}")
            except Exception as e_shut_gen:
                 print(f"Warning: Unexpected error during socket shutdown in stop_client: {e_shut_gen}")

            try:
                socket_to_close.close()
                print("[DEBUG] stop_client: Socket closed.")
            except socket.error as e_close:
                 print(f"Warning: Error closing socket in stop_client (already closed?): {e_close}")
            except Exception as e_close_gen:
                 print(f"Warning: Unexpected error closing socket in stop_client: {e_close_gen}")
            finally:
                 # Set global to None *only if* it's still the one we intended to close
                 if client_socket is socket_to_close:
                     client_socket = None
                     print("[DEBUG] stop_client: Global client_socket set to None.")
                 else:
                     print("[DEBUG] stop_client: Global client_socket was changed by another thread, not setting to None here.")
        else:
            print("[DEBUG] stop_client: client_socket was already None.")


    # Wait for the receive_messages thread to finish (with timeout)
    if client_thread and client_thread.is_alive():
        print(f"[DEBUG] stop_client: Waiting for receive_messages thread {client_thread.name} to join...")
        client_thread.join(timeout=2.0)
        if client_thread.is_alive():
             print("[DEBUG] stop_client: receive_messages thread did not join in time.")
        else:
             print("[DEBUG] stop_client: receive_messages thread joined.")
    
    if callback:
        callback("Voice recognition client stopped")
    
    return True

def send_configuration(model, method, callback=None):
    """Send the selected model and method configuration to the server"""
    global client_socket, socket_lock
    with socket_lock: # Acquire lock
        if not client_socket:
            if callback:
                callback({"status": "error", "message": "Not connected to server"})
            return False
        try:
            message_data = {
                "type": "configure",
                "model": model,
                "method": method
            }
            message = json.dumps(message_data)
            client_socket.sendall(message.encode()) # Use locked socket
            print(f"Sent configuration: Model={model}, Method={method}") # Replaced logger with print
            if callback:
                callback({"status": "info", "message": f"Configuration sent (Model: {model}, Method: {method})"})
            return True
        except socket.error as e:
            error_msg = f"Socket error sending configuration: {e}"
            print(error_msg) # Replaced logger with print
            if callback:
                callback({"status": "error", "message": error_msg})
            # Consider closing socket here? Maybe better handled by receive loop
            return False
        except Exception as e:
            error_msg = f"Error sending configuration: {e}"
            print(error_msg) # Replaced logger with print
            if callback:
                 callback({"status": "error", "message": error_msg})
            return False

def send_context_response(request_id, context_dict, callback=None):
    """Send the gathered Blender context back to the server for a specific request"""
    global client_socket, socket_lock
    with socket_lock: # Acquire lock
        if not client_socket:
            # No callback here, as this is usually triggered internally
            print("Cannot send context response: Not connected to server.") # Replaced logger with print
            return False
        try:
            message_data = {
                "type": "context_response",
                "request_id": request_id,
                "context": context_dict
            }
            message = json.dumps(message_data)
            print(f"[DEBUG] send_context_response: Sending: {message}")
            client_socket.sendall(message.encode()) # Use locked socket
            print(f"[DEBUG] send_context_response: Successfully sent context for request_id: {request_id}")
            return True
        except socket.error as e:
            print(f"[DEBUG] send_context_response: Socket error sending context for {request_id}: {e}")
            # Consider closing socket here? Maybe better handled by receive loop
            return False
        except Exception as e:
            print(f"Error sending context response for {request_id}: {e}") # Replaced logger with print
            return False


def send_text_command(text, callback=None):
    """Send a text command directly to the server for processing"""
    global client_socket, socket_lock
    with socket_lock: # Acquire lock
        if not client_socket:
            if callback:
                callback({"status": "error", "message": "Not connected to server"})
            return False

        try:
            # Gather current Blender context
            current_context = get_blender_context()

            # Construct message with context
            message_data = {
                "type": "process_text",
                "text": text,
                "context": current_context # Add context here
            }
            message = json.dumps(message_data)
            client_socket.sendall(message.encode()) # Use locked socket
            if callback:
                # Provide immediate feedback that the text was sent
                callback({"status": "info", "message": f"Sent text command: {text}"})
            return True
        except socket.error as e:
            if callback:
                # Report the error but don't stop the client here.
                # Let the receive thread handle persistent connection issues.
                callback({"status": "error", "message": f"Socket error sending text command: {e}"})
            # Consider closing socket here? Maybe better handled by receive loop
            return False # Indicate send failure
        except Exception as e:
            if callback:
                 callback({"status": "error", "message": f"Error sending text command: {e}"})
            return False


# For testing as standalone script
if __name__ == "__main__":
    # Setup basic logging for standalone testing
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__) # Use __name__ for logger

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
