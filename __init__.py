bl_info = {
    "name": "Articulate 3D",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Voice",
    "description": "Control Blender using voice commands with Gemini AI",
    "category": "3D View",
}

import bpy
import os
import json
import requests
import re
import threading
import time
import logging # Import logging
import sys # Import sys
from pathlib import Path
import collections # Import collections for deque
# Removed top-level imports for blender_voice_client and importlib

# --- Logging Setup ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_file = Path(__file__).parent / 'articulate3d_addon.log' # Log file in project root

# Configure root logger for console output (Blender's console)
logging.basicConfig(level=logging.INFO, format=log_format, handlers=[logging.StreamHandler(sys.stdout)])

# Create a specific logger for this addon module
logger = logging.getLogger("Articulate3DAddon")
logger.setLevel(logging.INFO) # Ensure logger level is set

# Add file handler
try:
    file_handler = logging.FileHandler(log_file, mode='a') # Use append mode
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)
    logger.info(f"--- Addon Log session started. Logging to {log_file} ---")
except Exception as e:
    # Use root logger (prints to Blender console) if specific logger fails
    logging.error(f"Failed to set up file logging to {log_file}: {e}")

# --- End Logging Setup ---

# Function to update the .env file with the API key
def update_env_file(api_key):
    """Update the .env file with the provided API key"""
    env_path = Path(__file__).parent / '.env'
    
    # Create .env file from example if it doesn't exist
    if not env_path.exists():
        example_path = Path(__file__).parent / '.env.example'
        if example_path.exists():
            with open(example_path, 'r') as example, open(env_path, 'w') as env:
                env.write(example.read())
        else:
            # Create a basic .env file
            with open(env_path, 'w') as env:
                env.write("# Articulate 3D Environment Configuration\n")
                env.write("# Add your API keys below\n\n")
                env.write("# Google Gemini API Key\n")
                env.write(f"GEMINI_API_KEY={api_key}\n")
                return
    
    # Read the current .env file
    with open(env_path, 'r') as file:
        content = file.read()
    
    # Update or add the GEMINI_API_KEY
    if 'GEMINI_API_KEY=' in content:
        # Replace the existing key
        content = re.sub(r'GEMINI_API_KEY=.*', f'GEMINI_API_KEY={api_key}', content)
    else:
        # Add the key if it doesn't exist
        content += f"\n# Google Gemini API Key\nGEMINI_API_KEY={api_key}\n"
    
    # Write the updated content back to the file
    with open(env_path, 'w') as file:
        file.write(content)

# Global variables
voice_client_thread = None
script_queue = []
command_history = collections.deque(maxlen=20) # Main history (temporary)
starred_commands = [] # Persistent starred commands list
last_transcription = None
pending_transcriptions = {} # request_id: transcription mapping

# --- Helper Functions ---
def find_history_entry_by_timestamp(timestamp):
    """Find index of an entry in command_history by timestamp."""
    for i, entry in enumerate(command_history):
        if entry.get('timestamp') == timestamp:
            return i
    return -1

def find_starred_entry_by_timestamp(timestamp):
    """Find index of an entry in starred_commands by timestamp."""
    for i, entry in enumerate(starred_commands):
        if entry.get('timestamp') == timestamp:
            return i
    return -1

# --- Property Group ---
class VoiceCommandProperties(bpy.types.PropertyGroup):
    is_listening: bpy.props.BoolProperty(name="Is Listening", default=False)
    api_key: bpy.props.StringProperty(
        name="API Key", description="Your Google Gemini API Key",
        default="", subtype='PASSWORD', update=lambda self, context: update_env_file(self.api_key)
    )
    selected_model: bpy.props.EnumProperty(
        items=[
            # Updated model list - check exact names from Google AI Studio/docs if needed
            ("gemini-2.0-flash", "Gemini 2.0 Flash", "Fast model for general tasks"),
            ("gemini-2.5-pro-exp-03-25", "Gemini 2.5 Pro Exp", "Latest advanced model (Experimental)"),
            # Add other relevant models if desired, e.g., older stable ones
            # ("gemini-1.5-pro-latest", "Gemini 1.5 Pro", "Previous generation Pro model"),
            # ("gemini-1.5-flash-latest", "Gemini 1.5 Flash", "Previous generation Flash model"),
        ], name="Gemini Model", default="gemini-2.0-flash"
    )
    audio_method: bpy.props.EnumProperty(
        items=[
            ("gemini", "Gemini Direct", "Process audio directly with Gemini (Fastest)"),
            ("whisper", "Whisper", "Transcribe with Whisper (Base model)"),
            ("google_stt", "Google Cloud STT", "Transcribe with Google STT (Requires Cloud setup)"),
        ], name="Audio Method", default="whisper",
        description="Method used to process voice commands"
    )
    console_output: bpy.props.StringProperty(name="Console Output", default="Ready...", maxlen=1024)
    show_history: bpy.props.BoolProperty(name="Show Command History", default=True)
    show_starred: bpy.props.BoolProperty(name="Show Starred Commands", default=False)

# --- Core Functions ---
def update_console(context, text):
    props = context.scene.voice_command_props
    props.console_output = text
    logger.info(text)

def handle_script(context, script):
    try:
        script_queue.append(script)
        update_console(context, f"Received script to execute")
    except Exception as e:
        logger.error(f"Error handling script: {str(e)}", exc_info=True)
        update_console(context, f"Error handling script: {str(e)}")

import json # Add json import for safe string conversion

def process_voice_client_message(context, message):
    global last_transcription, command_history, pending_transcriptions # Added pending_transcriptions
    try:
        # Ensure message is logged safely as a string
        log_message_str = json.dumps(message) if isinstance(message, dict) else str(message)
        logger.debug(f"Processing message: {log_message_str[:500]}") # Log truncated message safely

        if isinstance(message, str):
            update_console(context, message)
        elif isinstance(message, dict):
            status = message.get("status", "unknown")
            msg_text = message.get("message", "No message content.")
            request_id = message.get("request_id") # Get request ID if present

            if status == "request_context":
                # Server is asking for context for a voice command
                logger.info(f"Received context request {request_id}: {msg_text}")
                update_console(context, f"Server: {msg_text}") # Show transcription/status

                # Store the transcription text associated with this request ID
                if request_id and msg_text:
                    # Clean up the message text to get the core transcription
                    cleaned_transcription = msg_text.replace("Processing audio command with Gemini...", "").replace("Transcribed command (Whisper):", "").replace("Transcribed command (Google STT):", "").strip()
                    if cleaned_transcription:
                         pending_transcriptions[request_id] = cleaned_transcription
                         logger.debug(f"Stored transcription for {request_id}: '{cleaned_transcription}'")
                    else:
                         logger.warning(f"Could not extract clean transcription from context request message for {request_id}: {msg_text}")
                         pending_transcriptions[request_id] = f"Voice Command ({request_id})" # Fallback

                # Immediately gather and send context back
                try:
                    import sys, os
                    addon_dir = os.path.dirname(os.path.abspath(__file__))
                    if addon_dir not in sys.path: sys.path.insert(0, addon_dir)
                    import blender_voice_client
                    context_dict = blender_voice_client.get_blender_context()
                    blender_voice_client.send_context_response(request_id, context_dict)
                    logger.debug(f"Sent context response for {request_id}")
                except Exception as e:
                    logger.error(f"Failed to send context response for {request_id}: {e}", exc_info=True)
                    update_console(context, f"Error sending context: {e}")

            elif status == "transcribed":
                last_transcription = msg_text.replace("Transcribed: ", "").strip()
                update_console(context, f"Server: {msg_text}")
            elif status == "script":
                script_content = message.get("script", "")
                original_text = message.get("original_text") # Text from edited command (e.g., direct text input)
                command_text = "Unknown Command" # Default

                # Determine the source description for the history
                if original_text:
                    command_text = original_text # Prefer text command origin if available
                elif request_id in pending_transcriptions:
                    command_text = pending_transcriptions.pop(request_id) # Retrieve and remove stored transcription
                    logger.debug(f"Retrieved transcription for {request_id}: '{command_text}'")
                elif request_id:
                    command_text = f"Voice Command ({request_id})" # Fallback if ID exists but no transcription was stored
                    logger.warning(f"No pending transcription found for script request {request_id}. Using fallback.")
                else:
                     logger.error("Received script message with neither original_text nor request_id.")
                     command_text = "Unknown Script Source" # Absolute fallback

                # Process the script (or lack thereof)
                if script_content:
                    # Queue script, transcription, AND request_id
                    script_queue.append((script_content, command_text, request_id))
                    update_console(context, f"Received script for '{command_text}' - queued.")
                else:
                    # Script generation failed on the server side
                    logger.warning(f"Received script message status but no script content for '{command_text}' (Request ID: {request_id}).")
                    update_console(context, f"Script generation failed for '{command_text}'.")
                    # Log failed attempt to history
                    entry = {
                        'transcription': command_text, # Use the determined command_text
                        'status': 'Failed Generation',
                        'script': None, 'timestamp': time.time(), 'starred': False
                    }
                    command_history.append(entry)
                    # Clean up pending transcription if it somehow still exists for this ID
                    if request_id in pending_transcriptions:
                        del pending_transcriptions[request_id]


            elif status == "error":
                error_msg = f"Server Error: {msg_text}"
                # Attempt to link error back to a pending transcription if possible
                linked_transcription = "Unknown Command"
                if request_id and request_id in pending_transcriptions:
                    linked_transcription = pending_transcriptions.pop(request_id) # Retrieve and remove
                    logger.debug(f"Retrieved transcription for error message {request_id}: '{linked_transcription}'")
                elif request_id:
                    linked_transcription = f"Voice Command ({request_id})" # Fallback
                logger.error(error_msg)
                update_console(context, error_msg)
                # Log error to history, using the linked transcription if found
                entry = {
                    'transcription': linked_transcription,
                    'status': 'Server Error',
                    'script': None, 'timestamp': time.time(), 'starred': False
                }
                command_history.append(entry)
                logger.debug(f"Appended server error to command_history: {entry}")


            elif status in ["info", "ready", "stopped"]:
                 logger.info(f"Received status '{status}': {msg_text}")
                 update_console(context, f"Server: {msg_text}")
            else:
                logger.warning(f"Received message with unhandled status: {status}")
                update_console(context, f"Server: {msg_text}")
        else:
            logger.warning(f"Received unexpected message format: {type(message)} - {message}")
            update_console(context, str(message))
    except Exception as e:
            # Log the raw error details for better debugging
            ui_error_msg = f"Error processing message: {str(e)}"
            logger.error(f"Error processing message: {str(e)}. Raw message: {log_message_str[:500]}", exc_info=True)
            update_console(context, ui_error_msg)

def execute_scripts_timer():
    global command_history
    context = bpy.context
    needs_redraw = False
    if script_queue:
        # Unpack script, transcription, AND request_id
        script_to_execute, transcription, request_id = script_queue.pop(0)
        logger.debug(f"Dequeued script for transcription: '{transcription}' (Request ID: {request_id})")
        status = 'Unknown'
        entry_timestamp = time.time()
        try:
            # Log context before execution
            logger.info(f"Context before exec: area={context.area.type if context.area else 'None'}, window={context.window.screen.name if context.window else 'None'}, mode={context.mode if hasattr(context, 'mode') else 'N/A'}")
            update_console(context, f"Executing script for: {transcription}")

            # Execute the script
            exec(script_to_execute, {"bpy": bpy})

            status = 'Success'
            update_console(context, f"Script for '{transcription}' executed successfully.")
        except Exception as e:
            status = 'Script Error'
            error_type = type(e).__name__
            error_message = str(e)
            ui_error_msg = f"Script Execution Error for '{transcription}': {error_type} - {error_message}"
            # Log detailed traceback
            logger.error(f"Script Execution Error for '{transcription}' (Request ID: {request_id}):", exc_info=True)
            update_console(context, ui_error_msg)

            # --- Send error back to server ---
            try:
                import sys, os
                addon_dir = os.path.dirname(os.path.abspath(__file__))
                if addon_dir not in sys.path: sys.path.insert(0, addon_dir)
                import blender_voice_client
                if hasattr(blender_voice_client, 'send_execution_error'):
                    logger.info(f"Sending execution error details back to server for request {request_id}...")
                    blender_voice_client.send_execution_error(request_id, error_type, error_message)
                else:
                    # This case should ideally not happen if client is updated
                    logger.warning("blender_voice_client.send_execution_error function not found.")
            except Exception as send_err:
                logger.error(f"Failed to send execution error to server: {send_err}", exc_info=True)
            # --- End error sending ---

        # Always add to history
        entry = {
            'transcription': transcription, 'status': status,
            'script': script_to_execute, 'timestamp': entry_timestamp,
            'starred': False # New entries are never starred by default
        }
        command_history.append(entry)
        logger.debug(f"Appended to command_history: {entry}")
        needs_redraw = True
        # Removed redundant check for transcription before adding to history

    if needs_redraw:
        logger.debug("Tagging UI for redraw.")
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()
    return 0.5

# --- Operators ---
class BLENDER_OT_voice_command(bpy.types.Operator):
    bl_idname = "wm.voice_command"
    bl_label = "Start Voice Command"

    def validate_api_key(self, api_key):
        """Checks if the provided Gemini API key is valid by making a simple request."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            response = requests.get(url)
            if response.status_code == 200: return True
            else:
                error_msg = response.json().get('error', {}).get('message', 'Unknown API error')
                logger.error(f"API key validation failed: {error_msg} (Status code: {response.status_code})")
                self.report({'ERROR'}, f"API Key Validation Failed: {error_msg}")
                return False
        except requests.exceptions.RequestException as e:
             logger.error(f"API key validation failed due to network error: {str(e)}", exc_info=True)
             self.report({'ERROR'}, f"Network Error during API Key Validation: {e}")
             return False
        except Exception as e:
            logger.error(f"Unexpected error during API key validation: {str(e)}", exc_info=True)
            self.report({'ERROR'}, f"Unexpected Error during API Key Validation: {e}")
            return False

    def execute(self, context):
        props = context.scene.voice_command_props
        if not props.api_key:
            self.report({'ERROR'}, "Please enter your Gemini API key first")
            return {'CANCELLED'}
        try:
            import sys, os
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            if addon_dir not in sys.path: sys.path.insert(0, addon_dir)
            import blender_voice_client
            update_env_file(props.api_key)
            update_console(context, "Validating API key...")
            if not self.validate_api_key(props.api_key):
                update_console(context, "API key validation failed.")
                props.is_listening = False
                return {'CANCELLED'}
            props.is_listening = True
            update_console(context, "Starting voice recognition...")
            success = blender_voice_client.start_client(lambda msg: process_voice_client_message(context, msg))
            if not success:
                ui_error_msg = "Failed to start/connect to voice server."
                self.report({'ERROR'}, ui_error_msg)
                update_console(context, ui_error_msg)
                props.is_listening = False
                return {'CANCELLED'}

            # Send configuration immediately after successful connection
            logger.info("Sending configuration to server...")
            config_success = blender_voice_client.send_configuration(
                props.selected_model,
                props.audio_method,
                callback=lambda msg: process_voice_client_message(context, msg) # Use existing handler for feedback
            )
            if not config_success:
                 ui_error_msg = "Failed to send configuration to server."
                 self.report({'ERROR'}, ui_error_msg)
                 update_console(context, ui_error_msg)
                 # Stop the client if config fails? Or let it run? For now, stop.
                 blender_voice_client.stop_client(lambda msg: update_console(context, msg))
                 props.is_listening = False
                 return {'CANCELLED'}

            # Register timer only after successful connection and config send
            if not bpy.app.timers.is_registered(execute_scripts_timer):
                bpy.app.timers.register(execute_scripts_timer)

            update_console(context, "Client connected and configured. Listening...")
            return {'FINISHED'}
        except Exception as e:
            props.is_listening = False
            error_msg = f"Error starting voice command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

class BLENDER_OT_stop_voice_command(bpy.types.Operator):
    bl_idname = "wm.stop_voice_command"
    bl_label = "Stop Voice Command"
    def execute(self, context):
        props = context.scene.voice_command_props
        try:
            import sys, os
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            if addon_dir not in sys.path: sys.path.insert(0, addon_dir)
            import blender_voice_client
            update_console(context, "Stopping voice recognition...")
            blender_voice_client.stop_client(lambda msg: update_console(context, msg))
            if bpy.app.timers.is_registered(execute_scripts_timer):
                bpy.app.timers.unregister(execute_scripts_timer)
            props.is_listening = False
            return {'FINISHED'}
        except Exception as e:
            error_msg = f"Error stopping voice recognition client: {str(e)}"
            logger.error(error_msg, exc_info=True)
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            props.is_listening = False
            return {'CANCELLED'}

class BLENDER_OT_execute_history_command(bpy.types.Operator):
    bl_idname = "wm.execute_history_command"
    bl_label = "Execute History Command"
    bl_options = {'REGISTER', 'UNDO'}
    history_index: bpy.props.IntProperty(name="History Index")
    is_starred_execution: bpy.props.BoolProperty(name="Is Starred Execution", default=False) # Flag if run from starred list

    @classmethod
    def description(cls, context, properties):
        try:
            # Determine if we are looking in history or starred list
            source_list = starred_commands if properties.is_starred_execution else command_history
            entry = list(source_list)[properties.history_index] # Adjust index logic if needed for starred
            return f"Execute: {entry.get('transcription', 'Unknown Command')}"
        except IndexError:
            return "Execute command"

    def execute(self, context):
        global command_history # Need to modify history for re-run entry
        try:
            # Determine source list based on flag
            source_list = starred_commands if self.is_starred_execution else command_history
            
            # Adjust index access if starred_commands list is used directly
            # For simplicity, assume history_index refers to the original index in command_history
            # We might need a more robust way to link starred items back if history clears
            
            # Find the entry in the main history using timestamp if possible, otherwise index
            entry_to_execute = None
            if self.is_starred_execution:
                 # Find by timestamp in main history
                 starred_entry = starred_commands[self.history_index] # Get starred item
                 ts = starred_entry.get('timestamp')
                 hist_idx = find_history_entry_by_timestamp(ts)
                 if hist_idx != -1:
                     entry_to_execute = command_history[hist_idx]
                 else: # Fallback if not found in history (e.g. history cleared)
                     entry_to_execute = starred_entry # Use the starred entry itself
            else:
                 entry_to_execute = list(command_history)[self.history_index]


            if not entry_to_execute:
                 self.report({'ERROR'}, "Could not find command entry to execute.")
                 return {'CANCELLED'}

            script_to_execute = entry_to_execute.get('script')
            original_transcription = entry_to_execute.get('transcription', 'Unknown Command')

            # --- Added Check: Ensure script exists before trying to execute ---
            if not script_to_execute or not script_to_execute.strip():
                error_msg = f"No valid script found in history item: '{original_transcription}'"
                logger.warning(error_msg)
                self.report({'WARNING'}, error_msg)
                update_console(context, error_msg)
                return {'CANCELLED'} # Do not proceed

            update_console(context, f"Executing {'starred' if self.is_starred_execution else 'history'} command: {original_transcription}")
            logger.info(f"Executing {'starred' if self.is_starred_execution else 'history'} script (index {self.history_index}): {original_transcription}")
            # Add debug log to confirm script content before execution
            logger.debug(f"Script content for execution:\n---\n{script_to_execute}\n---")

            status = 'Unknown'
            try:
                exec(script_to_execute, {"bpy": bpy})
                status = 'Success (Executed)'
                update_console(context, "Script executed successfully.")
            except Exception as e:
                status = 'Script Error (Executed)'
                ui_error_msg = f"Script Execution Error: {type(e).__name__} - {str(e)}"
                # Use exc_info=True for detailed traceback in the log file
                logger.error(f"Error executing history script '{original_transcription}':", exc_info=True)
                update_console(context, ui_error_msg) # Show simplified error in UI console
                self.report({'ERROR'}, ui_error_msg) # Report error to Blender UI

            # Add a NEW entry to the main history, always unstarred
            # Ensure the script is actually passed here
            new_entry = {
                'transcription': f"{original_transcription} (Executed)",
                'status': status,
                'script': script_to_execute, # Pass the script that was attempted
                'timestamp': time.time(),
                'starred': False # Executed commands are never starred by default
            }
            command_history.append(new_entry)
            logger.debug(f"Appended execution attempt to command_history: {new_entry}")

            # Force UI redraw
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type == 'UI': region.tag_redraw()
            return {'FINISHED'}

        except IndexError:
            self.report({'ERROR'}, f"Invalid index: {self.history_index}")
            return {'CANCELLED'}
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}


class BLENDER_OT_toggle_star_history_command(bpy.types.Operator):
    bl_idname = "wm.toggle_star_history_command"
    bl_label = "Toggle Starred Status"
    bl_options = {'REGISTER'}
    history_index: bpy.props.IntProperty(name="History Index") # Index in command_history

    @classmethod
    def description(cls, context, properties):
        try:
            entry = list(command_history)[properties.history_index]
            action = "Unstar" if entry.get('starred', False) else "Star"
            return f"{action}: {entry.get('transcription', 'Unknown Command')}"
        except IndexError: return "Toggle Starred Status (Invalid Index)"
        except Exception: return "Toggle Starred Status"

    def execute(self, context):
        global command_history, starred_commands
        try:
            history_list = list(command_history)
            if 0 <= self.history_index < len(history_list):
                entry = history_list[self.history_index]
                entry_timestamp = entry.get('timestamp')
                is_currently_starred = entry.get('starred', False)

                # Toggle starred status in main history entry
                entry['starred'] = not is_currently_starred
                action = "Starred" if entry['starred'] else "Unstarred"
                logger.info(f"{action} history item at index {self.history_index}: {entry.get('transcription', 'N/A')}")

                # Update the separate starred_commands list
                starred_idx = find_starred_entry_by_timestamp(entry_timestamp)
                if entry['starred'] and starred_idx == -1: # Star it and not already in starred list
                    # Add a copy to starred list (only essential info)
                    starred_commands.append({
                        'transcription': entry.get('transcription'),
                        'script': entry.get('script'),
                        'timestamp': entry_timestamp # Link by timestamp
                    })
                    logger.debug(f"Added to starred_commands: {entry.get('transcription')}")
                elif not entry['starred'] and starred_idx != -1: # Unstar it and was in starred list
                    removed_starred = starred_commands.pop(starred_idx)
                    logger.debug(f"Removed from starred_commands: {removed_starred.get('transcription')}")

                # Recreate the main history deque
                new_history = collections.deque(history_list, maxlen=command_history.maxlen)
                command_history = new_history

                # Force UI redraw
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            for region in area.regions:
                                if region.type == 'UI': region.tag_redraw()
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, f"Invalid history index for starring: {self.history_index}")
                return {'CANCELLED'}
        except Exception as e:
            error_msg = f"Error toggling star status: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

class BLENDER_OT_delete_history_command(bpy.types.Operator):
    bl_idname = "wm.delete_history_command"
    bl_label = "Delete History Command"
    bl_options = {'REGISTER'}
    history_index: bpy.props.IntProperty(name="History Index")

    @classmethod
    def description(cls, context, properties):
        try:
            entry = list(command_history)[properties.history_index]
            return f"Remove '{entry.get('transcription', 'Unknown Command')}' from history (Does NOT affect starred status or undo scene changes)"
        except IndexError: return "Remove command from history (Invalid Index)"
        except Exception: return "Remove command from history (Does NOT affect starred status or undo scene changes)"

    def execute(self, context):
        global command_history
        try:
            history_list = list(command_history)
            if 0 <= self.history_index < len(history_list):
                removed_entry = history_list.pop(self.history_index)
                logger.info(f"Removing history item at index {self.history_index}: {removed_entry.get('transcription', 'N/A')}")
                new_history = collections.deque(history_list, maxlen=command_history.maxlen)
                command_history = new_history
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            for region in area.regions:
                                if region.type == 'UI': region.tag_redraw()
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, f"Invalid history index for deletion: {self.history_index}")
                return {'CANCELLED'}
        except Exception as e:
            error_msg = f"Error deleting history command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

# --- Panel ---
class BLENDER_PT_voice_command_panel(bpy.types.Panel):
    bl_label = "Voice Command Panel"
    bl_idname = "BLENDER_PT_voice_command"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Voice"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.voice_command_props
        
        # API Configuration
        api_box = layout.box()
        api_box.label(text="Configuration:", icon="SETTINGS")
        api_box.prop(props, "api_key")
        
        # Status
        status_box = layout.box()
        status_row = status_box.row()
        status_row.label(text="Status:")
        if props.is_listening:
            status_row.label(text="Listening...", icon="RADIOBUT_ON")
        else:
            status_row.label(text="Ready", icon="RADIOBUT_OFF")
        
        # Console output
        console_box = layout.box()
        console_box.label(text="Console Output:", icon="CONSOLE")
        console_box.prop(props, "console_output", text="") # Use empty text label

        # Model and Method Selection
        config_row = layout.row(align=True)
        config_row.prop(props, "selected_model")
        config_row.prop(props, "audio_method")

        # Command buttons
        buttons_row = layout.row(align=True)
        buttons_row.enabled = bool(props.api_key)
        buttons_row.scale_y = 2.0
        
        # Start button
        if not props.is_listening:
            start_btn = buttons_row.operator("wm.voice_command", text="Start Voice Command", icon="REC")
        # Stop button
        else:
            stop_btn = buttons_row.operator("wm.stop_voice_command", text="Stop Voice Command", icon="PAUSE")
        
        if not props.api_key:
            layout.label(text="⚠️ Please enter API key first", icon="ERROR")
        
        # Help section
        help_box = layout.box()
        help_box.label(text="Voice Command Examples:", icon="QUESTION")
        help_box.label(text="• Create a red cube")
        help_box.label(text="• Add a smooth sphere")
        help_box.label(text="• Move object up 2 units")


        # Command History section (Collapsible)
        history_box = layout.box()
        row = history_box.row()
        row.prop(props, "show_history", text="Command History", icon="TIME", emboss=False)
        # TODO: Add Starred Popup Button Here
        # row.operator("wm.show_starred_popup", text="", icon='SOLO_ON') # Example

        if not props.show_history: # Show only when collapsed
            col = history_box.column(align=True)
            if not command_history:
                col.label(text="No commands yet.")
            else:
                # Display ALL entries (newest first)
                for i, entry in enumerate(reversed(command_history)):
                    row = col.row(align=True)
                    status = entry.get('status', 'Unknown')
                    transcription = entry.get('transcription', 'N/A')
                    script = entry.get('script')
                    original_index = len(command_history) - 1 - i # Index in the current deque

                    status_icon = "CHECKMARK" if 'Success' in status else "ERROR" if 'Error' in status or 'Failed' in status else "INFO"
                    star_icon = 'SOLO_ON' if entry.get('starred', False) else 'SOLO_OFF'

                    # Use split factor to manage layout
                    split = row.split(factor=0.75) # Adjust factor as needed

                    # Command text/button
                    if script:
                        op = split.operator("wm.execute_history_command", text=f"{transcription}", icon=status_icon)
                        op.history_index = original_index
                        op.is_starred_execution = False # Executing from main history
                    else:
                        split.label(text=f"{transcription}", icon=status_icon)

                    # Status label and buttons
                    row_right = split.row(align=True)
                    row_right.alignment = 'RIGHT'
                    row_right.label(text=f"({status})")
                    # Star button
                    star_op = row_right.operator("wm.toggle_star_history_command", text="", icon=star_icon)
                    star_op.history_index = original_index
                    # Delete button
                    del_op = row_right.operator("wm.delete_history_command", text="", icon='TRASH')
                    del_op.history_index = original_index


        # --- Starred Commands Section (Collapsible) ---
        starred_box = layout.box()
        row = starred_box.row()
        row.prop(props, "show_starred", text="Starred Commands", icon="SOLO_ON", emboss=False)

        if not props.show_starred: # Show only when collapsed
            col_starred = starred_box.column(align=True)
            if not starred_commands:
                col_starred.label(text="No starred commands yet.")
            else:
                # Iterate through the separate starred list
                for i, entry in enumerate(starred_commands):
                    row_starred = col_starred.row(align=True)
                    transcription = entry.get('transcription', 'N/A')
                    script = entry.get('script')
                    entry_timestamp = entry.get('timestamp') # Get timestamp to find original index

                    # Find original index in command_history (needed for execution/unstarring)
                    # This might be fragile if history clears often. Consider storing index if needed.
                    original_index = find_history_entry_by_timestamp(entry_timestamp)

                    if script and original_index != -1:
                         # Execute button (uses original index)
                        op = row_starred.operator("wm.execute_history_command", text=f"{transcription}", icon='PLAY')
                        op.history_index = original_index
                        op.is_starred_execution = True # Mark as starred execution

                        # Unstar button (uses original index)
                        unstar_op = row_starred.operator("wm.toggle_star_history_command", text="", icon='SOLO_ON')
                        unstar_op.history_index = original_index
                    elif script: # Script exists but original history entry might be gone
                         row_starred.label(text=f"{transcription} (History Cleared?)", icon='PLAY')
                         # Simple remove from starred list operator needed here?
                         # For now, unstar still works if we pass the index *within starred_commands*
                         # This requires modifying the toggle operator or adding a new one.
                         # Let's stick to modifying toggle for now, passing a flag?
                         # Or maybe store the original index *in* the starred entry?
                         # Simplest for now: just show unstar, it will fail gracefully if index is bad
                         unstar_op = row_starred.operator("wm.toggle_star_history_command", text="", icon='SOLO_ON')
                         unstar_op.history_index = original_index # This index is wrong now...
                         # TODO: Fix unstarring if original history item is gone.
                    else:
                        row_starred.label(text=f"{transcription} (No Script)", icon='ERROR')
                        # Unstar button (index might be wrong here too)
                        unstar_op = row_starred.operator("wm.toggle_star_history_command", text="", icon='SOLO_ON')
                        unstar_op.history_index = original_index


# --- Registration ---
classes = (
    VoiceCommandProperties,
    BLENDER_OT_voice_command,
    BLENDER_OT_stop_voice_command,
    BLENDER_OT_execute_history_command,
    BLENDER_OT_toggle_star_history_command, # Register star operator
    BLENDER_OT_delete_history_command,
    BLENDER_PT_voice_command_panel,
)

def register():
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.types.Scene.voice_command_props = bpy.props.PointerProperty(type=VoiceCommandProperties)
        # Attempt to load API key from .env file on registration
        try:
            env_path = Path(__file__).parent / '.env'
            if env_path.exists():
                with open(env_path, 'r') as file:
                    content = file.read()
                    match = re.search(r'GEMINI_API_KEY=([^\n\r]*)', content)
                    if match and match.group(1) and match.group(1) != 'your_gemini_api_key_here':
                        try:
                            if hasattr(bpy.context, 'scene'):
                                bpy.context.scene.voice_command_props.api_key = match.group(1)
                            elif hasattr(bpy.data, 'scenes') and bpy.data.scenes:
                                for scene in bpy.data.scenes:
                                    scene.voice_command_props.api_key = match.group(1)
                        except AttributeError:
                            logger.warning("Could not set API key to scenes - will be loaded from .env when needed")
        except Exception as env_error:
            logger.error(f"Error loading API key from .env: {str(env_error)}", exc_info=True)
        logger.info("Articulate 3D Add-on registered successfully!")
    except Exception as e:
        logger.critical(f"Error registering Articulate 3D Add-on: {str(e)}", exc_info=True)


def unregister():
    try:
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        del bpy.types.Scene.voice_command_props
        logger.info("Articulate 3D Add-on unregistered.")
    except Exception as e:
        logger.error(f"Error unregistering Articulate 3D Add-on: {str(e)}", exc_info=True)

if __name__ == "__main__":
    register()
