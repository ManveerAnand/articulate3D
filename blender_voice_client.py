import os
import sys
import json
import socket
import threading
import subprocess
import time # Added for retry delay
import struct # Added for message framing
from pathlib import Path
import bpy # Import bpy for context gathering

# Socket client configuration
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

# Flag to signal the client to stop
stop_flag = threading.Event()

# Global variables for connection management
client_socket = None
client_thread = None

# --- Context Gathering ---
def get_blender_context():
    """Gathers relevant context from Blender's current state."""
    start_time = time.perf_counter() # Start timing
    print("[CLIENT DEBUG] get_blender_context: Starting context gathering...") # Log start
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

            # Get names of ALL objects in the scene's collections recursively
            all_scene_objects = []
            def get_objects_recursive(collection):
                for obj in collection.objects:
                    if obj.name not in all_scene_objects: # Avoid duplicates if linked
                        all_scene_objects.append(obj.name)
                for child_coll in collection.children:
                    get_objects_recursive(child_coll)

            if bpy.context.scene.collection:
                get_objects_recursive(bpy.context.scene.collection)
            context_data["scene_objects"] = all_scene_objects

    except Exception as e:
        # Removed problematic operator call from except block
        print(f"Error getting Blender context: {e}") # Keep print for console
        # Optionally report to Blender's info area:
        # bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=f"Context Error: {e}"), title="Articulate3D Error", icon='ERROR')
    finally:
        end_time = time.perf_counter() # End timing
        duration = end_time - start_time
        print(f"[CLIENT DEBUG] get_blender_context: Finished gathering. Duration: {duration:.4f} seconds") # Log duration

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
        
        # Give the server more time to start up, load models, and initialize audio
        import time
        print("[CLIENT INFO] Waiting 5 seconds for server to initialize...")
        time.sleep(5) # Increased delay
        print("[CLIENT INFO] Finished waiting for server.")
        
        return process
    except Exception as e:
        print(f"Error starting voice server: {e}")
        return None

def connect_to_server(callback=None):
    """Connect to the voice recognition server with retries"""
    global client_socket
    max_retries = 5
    last_error = None

    for attempt in range(max_retries):
        try:
            # Create a socket object
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Connect to the server
            client_socket.connect((HOST, PORT))

            if callback:
                callback("Connected to voice recognition server")

            return True # Connection successful
        except Exception as e:
            last_error = e
            if client_socket: # Close the socket if connection failed
                try:
                    client_socket.close()
                except: pass # Ignore errors during close
                client_socket = None

            if attempt < max_retries - 1:
                if callback:
                    # Optional: Log retry attempt
                    # callback(f"Connection attempt {attempt + 1} failed. Retrying in 1 second...")
                    pass
                time.sleep(1) # Wait before retrying
            else:
                # Last attempt failed
                if callback:
                    callback(f"Error connecting to server after {max_retries} attempts: {last_error}")
                return False

    # Should not be reached if logic is correct, but return False just in case
    return False

def receive_messages(callback=None):
    """Receive messages from the server"""
    global client_socket
    
    if not client_socket:
        if callback:
            callback("Not connected to server")
        return

    message_buffer = "" # Buffer to accumulate incoming data

    while not stop_flag.is_set():
        try:
            # Set a timeout to allow checking the stop flag
            client_socket.settimeout(0.5)

            # Receive data from the server
            data = client_socket.recv(4096)

            if not data:
                # Connection closed by server
                print("[CLIENT DEBUG] Socket recv returned empty. Connection closed by server.") # DEBUG
                if callback:
                    callback("Connection closed by server")
                # Process any remaining data in the buffer before breaking
                if message_buffer:
                    print(f"Processing remaining buffer on disconnect: {message_buffer}") # Debug print
                    # Attempt to process remaining buffer content (similar logic as below)
                    # This part might need refinement depending on expected message boundaries
                    try:
                        # Simple attempt: Assume remaining buffer is one message
                        message = json.loads(message_buffer)
                        # Process the message (duplicate code - consider refactoring)
                        if message.get("status") == "script":
                            script = message.get("script", "").replace("```python", "").replace("```", "").strip()
                            if script and callback:
                                print(f"\nExecuting script (from buffer):\n{script}\n")
                                callback({"status": "script", "message": "Received script", "script": script})
                        elif callback:
                            callback(message)
                    except json.JSONDecodeError as e_rem:
                        if callback:
                                callback(f"Error decoding remaining buffer: {e_rem}. Buffer: {message_buffer}")
                break # Exit loop after handling disconnect

            decoded_data = data.decode('utf-8')
            print(f"[CLIENT DEBUG] Received {len(data)} bytes. Decoded: '{decoded_data[:200]}...'") # DEBUG - Log received data (truncated)
            message_buffer += decoded_data
            print(f"[CLIENT DEBUG] Buffer size after adding: {len(message_buffer)}") # DEBUG

            # Process the buffer for complete JSON objects
            print(f"[CLIENT DEBUG] Starting buffer processing loop. Buffer: '{message_buffer[:200]}...'") # DEBUG
            decoder = json.JSONDecoder()
            scan_idx = 0 # Start scanning from the beginning of the buffer
            while scan_idx < len(message_buffer):
                # Skip leading whitespace
                while scan_idx < len(message_buffer) and message_buffer[scan_idx].isspace():
                    scan_idx += 1
                if scan_idx == len(message_buffer):
                    # Only whitespace left
                    message_buffer = "" # Clear buffer
                    break

                print(f"[CLIENT DEBUG] Attempting decoder.raw_decode at index {scan_idx}") # DEBUG
                try:
                    # Attempt to decode a JSON object starting at scan_idx
                    message, end_idx = decoder.raw_decode(message_buffer, scan_idx)
                    print(f"[CLIENT DEBUG] Successfully decoded JSON object ending at index {end_idx}. Status: {message.get('status', 'N/A')}") # DEBUG

                    # Successfully parsed, process the message
                    if message.get("status") == "script":
                        script = message.get("script", "").replace("```python", "").replace("```", "").strip()
                        # Corrected indentation for the inner if statement
                        if script and callback:
                            print(f"\nExecuting script:\n{script}\n")
                            callback({"status": "script", "message": "Received script", "script": script, "original_text": message.get("original_text")}) # Pass original_text
                    # Corrected indentation for the elif statement
                    elif callback:
                        callback(message) # Pass the full dictionary

                    # Remove the processed object from the buffer
                    message_buffer = message_buffer[end_idx:]
                    print(f"[CLIENT DEBUG] Removed processed JSON. Remaining buffer: '{message_buffer[:200]}...'") # DEBUG
                    scan_idx = 0 # Reset scan index for the potentially remaining buffer
                    # Continue the inner loop to check for more objects
                except json.JSONDecodeError as json_err:
                    # This means there isn't a complete JSON object starting at scan_idx
                    # in the current buffer. Stop scanning and wait for more data.
                    print(f"[CLIENT DEBUG] JSONDecodeError at index {scan_idx}: {json_err}. Waiting for more data. Buffer: '{message_buffer[scan_idx:scan_idx+100]}...'") # DEBUG
                    break # Exit the inner while loop, go back to waiting for socket data
                except Exception as inner_e:
                     # Catch other potential errors during buffer processing
                     print(f"[CLIENT DEBUG] Error during raw_decode: {type(inner_e).__name__} - {inner_e}. Buffer: {message_buffer[:200]}...") # DEBUG
                     if callback:
                         callback(f"Error processing message buffer: {inner_e}. Buffer: {message_buffer}")
                     # Decide whether to clear buffer or break outer loop based on error
                     message_buffer = "" # Clear buffer on unexpected error to prevent infinite loops
                     print("[CLIENT DEBUG] Cleared buffer due to unexpected inner error.") # DEBUG
                     break # Break inner loop

        except socket.timeout:
            # This is expected, just continue the loop
            # print("[CLIENT DEBUG] Socket recv timed out.") # Can be noisy, keep commented unless needed
            pass
        except socket.error as e: # Catch specific socket errors first
            if callback:
                callback(f"Socket error receiving message: {e}")
            break # Break outer loop on socket errors
        except UnicodeDecodeError as e:
             if callback:
                 callback(f"Error decoding received data: {e}")
             # Decide how to handle - potentially clear buffer or break
             message_buffer = "" # Clear potentially corrupt buffer
             continue # Or break? For now, continue.
        except Exception as outer_e: # Catch unexpected errors in the outer loop
             if callback:
                 callback(f"Unexpected error in receive loop: {outer_e}")
             break # Break outer loop on unexpected errors

    # Close the socket when done (loop exited)
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

# --- Helper Function for Framed Messaging ---
def send_framed_message(sock, message_dict, callback=None):
    """Encodes, frames, and sends a message dictionary."""
    try:
        message_json = json.dumps(message_dict)
        message_bytes = message_json.encode('utf-8')
        # Prepend message length as 4-byte unsigned integer (network byte order)
        header = struct.pack('!I', len(message_bytes))
        sock.sendall(header)
        sock.sendall(message_bytes)
        # Optional: Log successful send if needed, but keep it concise
        # print(f"[CLIENT DEBUG] Sent framed message: Type={message_dict.get('type', 'N/A')}, Length={len(message_bytes)}")
        return True
    except socket.error as e:
        error_msg = f"Socket error sending framed message: {e}"
        print(error_msg)
        if callback:
            callback({"status": "error", "message": error_msg})
        # Consider closing socket or signaling error more broadly if needed
        return False
    except Exception as e:
        error_msg = f"Error encoding/sending framed message: {e}"
        print(error_msg)
        if callback:
            callback({"status": "error", "message": error_msg})
        return False
# --- End Helper Function ---


def stop_client(callback=None):
    """Stop the voice recognition client"""
    global client_thread, client_socket
    
    # Signal the thread to stop
    stop_flag.set()
    
    # Let the receive_messages thread handle closing the socket when it exits.
    # Remove explicit socket closing here.
    # if client_socket:
    #     try:
    #         client_socket.close()
    #     except:
    #         pass
    #     client_socket = None
    
    # Wait for the receive_messages thread to finish (with timeout)
    if client_thread and client_thread.is_alive():
        client_thread.join(timeout=2.0)
    
    if callback:
        callback("Voice recognition client stopped")
    
    return True

def send_configuration(model, method, callback=None):
    """Send the selected model and method configuration to the server"""
    global client_socket
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
        # Corrected structure
        if send_framed_message(client_socket, message_data, callback):
            print(f"Sent configuration: Model={model}, Method={method}")
            if callback:
                callback({"status": "info", "message": f"Configuration sent (Model: {model}, Method: {method})"})
            return True
        else:
            # Error already printed/handled by send_framed_message
            return False
    except Exception as e:
        # Catch any unexpected error during the process
        error_msg = f"Unexpected error in send_configuration: {e}"
        print(error_msg)
        if callback:
            callback({"status": "error", "message": error_msg})
        return False

def send_context_response(request_id, context_dict, callback=None):
    """Send the gathered Blender context back to the server for a specific request"""
    global client_socket
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
        # Corrected structure
        if send_framed_message(client_socket, message_data, callback):
            print(f"Sent context response for request_id: {request_id}")
            return True
        else:
            # Error already printed/handled by send_framed_message
            return False
    except Exception as e:
        # Catch any unexpected error during the process
        error_msg = f"Unexpected error in send_context_response: {e}"
        print(error_msg)
        # No callback needed here usually
        return False


def send_text_command(text, callback=None):
    """Send a text command directly to the server for processing"""
    global client_socket
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
        # Corrected structure
        if send_framed_message(client_socket, message_data, callback):
            if callback:
                callback({"status": "info", "message": f"Sent text command: {text}"})
            return True
        else:
            # Error already printed/handled by send_framed_message
            return False
    except Exception as e:
        # Catch any unexpected error during the process
        error_msg = f"Unexpected error in send_text_command: {e}"
        print(error_msg)
        if callback:
            callback({"status": "error", "message": error_msg})
        return False

# --- New Function: Send Execution Error ---
# Modified signature to accept request_id explicitly
def send_execution_error(request_id, error_type, error_message, callback=None):
    """Send script execution error details back to the server."""
    global client_socket
    if not client_socket:
        print("[CLIENT ERROR] Cannot send execution error: Not connected to server.")
        if callback: callback({"status": "error", "message": "Cannot send execution error: Not connected"})
        return False
    try:
        message_data = {
            "type": "execution_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": error_message
        }
        # Corrected structure
        if send_framed_message(client_socket, message_data, callback):
            print(f"[CLIENT INFO] Sent execution error for request_id: {request_id}")
            if callback: callback({"status": "info", "message": "Execution error sent"})
            return True
        else:
            # Error already printed/handled by send_framed_message
            return False
    except Exception as e:
        # Catch any unexpected error during the process
        error_msg = f"Unexpected error in send_execution_error: {e}"
        print(error_msg)
        if callback:
            callback({"status": "error", "message": error_msg})
        return False
# --- End New Function ---


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
