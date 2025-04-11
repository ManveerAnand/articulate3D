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

# Global variables for voice client management
voice_client_thread = None
script_queue = []
command_history = collections.deque(maxlen=20) # History queue
last_transcription = None # Store the last transcription temporarily

# Property group to store addon settings
class VoiceCommandProperties(bpy.types.PropertyGroup):
    is_listening: bpy.props.BoolProperty(
        name="Is Listening",
        default=False
    )
    api_key: bpy.props.StringProperty(
        name="API Key",
        description="Your Google Gemini API Key",
        default="",
        subtype='PASSWORD',
        update=lambda self, context: update_env_file(self.api_key)
    )
    selected_model: bpy.props.EnumProperty(
        items=[
            ("gemini-2.0-flash", "Gemini 2.0 Flash", "Fast model for quick responses"),
            ("gemini-2.0-pro", "Gemini 2.0 Pro", "Advanced model with better reasoning"),
            ("gemini-2.0-thinking", "Gemini 2.0 Thinking", "Model optimized for complex reasoning"),
            ("gemini-1.5-flash", "Gemini 1.5 Flash", "Stable flash model")
        ],
        name="Gemini Model",
        default="gemini-2.0-flash"
    )
    console_output: bpy.props.StringProperty(
        name="Console Output",
        default="Ready...",
        maxlen=1024
    )
    show_history: bpy.props.BoolProperty(
        name="Show Command History",
        description="Expand or collapse the command history section",
        default=True # Start expanded by default
    )
    # Properties for editing history items
    editing_history_index: bpy.props.IntProperty(
        name="Editing History Index",
        description="Index of the history item currently being edited",
        default=-1 # -1 means nothing is being edited
    )
    edited_text: bpy.props.StringProperty(
        name="Edited Command Text",
        description="The text being edited for resubmission",
        default=""
    )

# Function to update console output
def update_console(context, text):
    # Keep updating the UI property
    props = context.scene.voice_command_props
    props.console_output = text
    # Also log the message
    logger.info(text)

# Function to handle received scripts
def handle_script(context, script):
    """Handle a script received from the voice recognition server"""
    try:
        # Add the script to the execution queue
        script_queue.append(script)
        update_console(context, f"Received script to execute")
    except Exception as e:
        logger.error(f"Error handling script: {str(e)}", exc_info=True)
        ui_error_msg = f"Error handling script: {str(e)}"
        update_console(context, ui_error_msg)

# Function to process messages from the voice client
def process_voice_client_message(context, message):
    """Process messages from the voice client"""
    global last_transcription # Allow modification of global
    try:
        logger.debug(f"Processing message: {message}") # Log raw message
        logger.debug(f"Value of last_transcription at start of function: {last_transcription}") # ADDED LOGGING
        # If it's a string, just update the console (likely simple status)
        if isinstance(message, str):
            update_console(context, message)
            # DO NOT clear last_transcription here anymore based on simple strings

        # If it's a dict, process based on status
        elif isinstance(message, dict):
            status = message.get("status", "unknown")
            msg_text = message.get("message", "No message content.")

            if status == "transcribed":
                last_transcription = msg_text.replace("Transcribed: ", "").strip() # Store transcription
                logger.debug(f"Value of last_transcription AFTER setting in 'transcribed' block: {last_transcription}") # ADDED LOGGING
                update_console(context, f"Server: {msg_text}")
            elif status == "script":
                script_content = message.get("script", "")
                logger.debug(f"Value of last_transcription BEFORE check in 'script' block: {last_transcription}") # ADDED LOGGING
                # Instead of adding to history here, add script and transcription to queue
                if last_transcription:
                    logger.debug(f"Queueing script for transcription: {last_transcription}")
                    script_queue.append((script_content, last_transcription)) # Add tuple to queue
                    update_console(context, f"Received script for '{last_transcription}' - queued for execution.")
                    last_transcription = None # Clear after use
                else:
                    # If no prior transcription, maybe just queue script? Or log warning?
                    logger.warning("Received script message but no prior transcription stored. Queueing script only.")
                    script_queue.append((script_content, None)) # Queue with None transcription
                    update_console(context, f"Server: {msg_text} (queued without transcription context)")

            elif status == "error":
                logger.error(f"Received error from server: {msg_text}")
                update_console(context, f"Server Error: {msg_text}")
                # Add error to history if it relates to the last transcription attempt
                if last_transcription:
                     logger.debug(f"Attempting to add error history for transcription: {last_transcription}")
                     entry = {
                        'transcription': last_transcription,
                        'status': 'Failed Generation/STT', # Or determine based on msg_text?
                        'script': None,
                        'timestamp': time.time()
                    }
                     command_history.append(entry)
                     logger.debug(f"Appended error to command_history: {entry}")
                     logger.debug(f"Current command_history size: {len(command_history)}")
                     last_transcription = None # Clear after use
                else:
                    logger.warning("Received error message but last_transcription was None.")
            # Removed clearing last_transcription based on info/ready/stopped statuses
            # It should only be cleared after being used for script queueing or error logging.
            elif status in ["info", "ready", "stopped"]: # Just log these statuses
                 logger.debug(f"Received status '{status}' message.")
                 update_console(context, f"Server: {msg_text}")
            else: # Other unknown statuses?
                logger.warning(f"Received message with unhandled status: {status}")
                update_console(context, f"Server: {msg_text}")
        # Handle cases where message is neither string nor dict
        else:
            logger.warning(f"Received unexpected message format: {type(message)} - {message}")
            update_console(context, str(message))
    except Exception as e:
        ui_error_msg = f"Error processing message from server: {str(e)}"
        logger.error(ui_error_msg, exc_info=True)
        update_console(context, ui_error_msg)

# Timer function to execute scripts from the queue
def execute_scripts_timer():
    """Timer function to execute scripts from the queue"""
    logger.debug("execute_scripts_timer called.") # Check if timer is running
    context = bpy.context
    props = context.scene.voice_command_props # Get props for context if needed
    
    needs_redraw = False # Flag to check if UI needs update
    # Check if there are any scripts in the queue
    if script_queue:
        # Get the next script tuple (script, transcription)
        script_to_execute, transcription = script_queue.pop(0)
        logger.debug(f"Dequeued script for transcription: {transcription}")

        status = 'Unknown' # Default status
        try:
            # Execute the script
            update_console(context, f"Executing script for: {transcription or 'Unknown command'}")
            exec(script_to_execute, {"bpy": bpy})
            status = 'Success'
            update_console(context, "Script executed successfully.")
        except Exception as e:
            status = 'Script Error'
            ui_error_msg = f"Script Execution Error: {str(e)}"
            logger.error(ui_error_msg, exc_info=True)
            update_console(context, ui_error_msg)
        
        # Add entry to history AFTER execution attempt
        if transcription: # Only add if we have the original transcription
             entry = {
                 'transcription': transcription,
                 'status': status,
                 'script': script_to_execute, # Store executed script
                 'timestamp': time.time()
             }
             command_history.append(entry)
             logger.debug(f"Appended to command_history after execution: {entry}")
             logger.debug(f"Current command_history size: {len(command_history)}")
        else:
              logger.warning("Script executed, but no transcription was associated; not adding to history.")
        
        if transcription: # If we added an entry, flag for redraw
             needs_redraw = True

    # Force UI redraw if history might have changed
    if needs_redraw:
        logger.debug("Tagging UI for redraw due to history update.")
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()
                            
    # Return interval to keep the timer running
    return 0.5  # Check every 0.5 seconds

# Operator to start voice command
class BLENDER_OT_voice_command(bpy.types.Operator):
    bl_idname = "wm.voice_command"
    bl_label = "Voice Command"
    
    def validate_api_key(self, api_key):
        """Validate the Gemini API key by making a simple HTTP request"""
        try:
            # Use requests library which is already imported at the top
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            response = requests.get(url)
            
            # Check if the response is successful (status code 200)
            if response.status_code == 200:
                return True
            else:
                error_msg = response.json().get('error', {}).get('message', 'Unknown API error')
                logger.error(f"API key validation failed: {error_msg} (Status code: {response.status_code})")
                # Provide slightly more context for the user report
                self.report({'ERROR'}, f"API Key Validation Failed: {error_msg}")
                return False
        except requests.exceptions.RequestException as e: # Catch specific network errors
             logger.error(f"API key validation failed due to network error: {str(e)}", exc_info=True)
             self.report({'ERROR'}, f"Network Error during API Key Validation: {e}")
             return False
        except Exception as e: # Catch other potential errors like JSON decoding
            logger.error(f"Unexpected error during API key validation: {str(e)}", exc_info=True)
            self.report({'ERROR'}, f"Unexpected Error during API Key Validation: {e}")
            return False
    
    def execute(self, context):
        props = context.scene.voice_command_props
        
        # Check if API key is provided
        if not props.api_key:
            self.report({'ERROR'}, "Please enter your Gemini API key first")
            return {'CANCELLED'}
        
        try:
            # Import voice client module directly to avoid relative import issues
            import sys
            import os
            # Add the addon directory to the path to ensure proper imports
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            if addon_dir not in sys.path:
                sys.path.insert(0, addon_dir)
            
            # Now import the blender_voice_client module
            import blender_voice_client
            
            # Update the .env file with the API key
            update_env_file(props.api_key)
            
            # Validate API key before proceeding
            update_console(context, "Validating API key...")
            is_valid = self.validate_api_key(props.api_key)
            
            if not is_valid:
                # Error already reported and logged by validate_api_key
                update_console(context, "API key validation failed. Please check your key and network connection.")
                # Make sure to reset the listening state
                props.is_listening = False
                return {'CANCELLED'}
            
            # Set listening state
            props.is_listening = True
            update_console(context, "Starting voice recognition...")
            
            # Start voice recognition client
            success = blender_voice_client.start_client(
                lambda msg: process_voice_client_message(context, msg)
            )
            
            if not success:
                ui_error_msg = "Failed to start or connect to voice recognition server. Check server logs."
                self.report({'ERROR'}, ui_error_msg)
                update_console(context, ui_error_msg)
                props.is_listening = False
                return {'CANCELLED'}
            
            # Start the timer to execute scripts
            if not bpy.app.timers.is_registered(execute_scripts_timer):
                bpy.app.timers.register(execute_scripts_timer)
            
            return {'FINISHED'}
        except ImportError as e:
             # Catch specific import errors if blender_voice_client is missing
            props.is_listening = False
            error_msg = f"Import Error: Failed to import blender_voice_client. Ensure it's in the correct path. Details: {str(e)}"
            logger.critical(error_msg, exc_info=True)
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        except Exception as e:
            # Catch other potential errors during startup
            props.is_listening = False
            error_msg = f"Error starting voice command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

# Operator to stop voice command
class BLENDER_OT_stop_voice_command(bpy.types.Operator):
    bl_idname = "wm.stop_voice_command"
    bl_label = "Stop Voice Command"
    
    def execute(self, context):
        props = context.scene.voice_command_props
        
        try:
            # Import voice client module directly to avoid relative import issues
            import sys
            import os
            # Add the addon directory to the path to ensure proper imports
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            if addon_dir not in sys.path:
                sys.path.insert(0, addon_dir)
            
            # Now import the blender_voice_client module
            import blender_voice_client
            
            # Stop the voice recognition
            update_console(context, "Stopping voice recognition...")
            blender_voice_client.stop_client(lambda msg: update_console(context, msg))
            
            # Unregister the timer if it's running
            if bpy.app.timers.is_registered(execute_scripts_timer):
                bpy.app.timers.unregister(execute_scripts_timer)
            
            # Reset the listening state
            props.is_listening = False
            
            return {'FINISHED'}
        except ImportError as e:
             # Catch specific import errors if blender_voice_client is missing
            error_msg = f"Import Error: Failed to import blender_voice_client. Ensure it's in the correct path. Details: {str(e)}"
            logger.critical(error_msg, exc_info=True)
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            # Still reset the listening state
        except Exception as e:
            error_msg = f"Error stopping voice recognition client: {str(e)}"
            logger.error(error_msg, exc_info=True)
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            # Still reset the listening state
            props.is_listening = False
            return {'CANCELLED'}

# Operator to execute a command from history
class BLENDER_OT_execute_history_command(bpy.types.Operator):
    bl_idname = "wm.execute_history_command"
    bl_label = "Execute History Command"
    bl_options = {'REGISTER', 'UNDO'} # Allow undo

    history_index: bpy.props.IntProperty(name="History Index")

    @classmethod
    def description(cls, context, properties):
        # Provide dynamic description based on the command
        try:
            entry = list(command_history)[properties.history_index]
            return f"Re-execute: {entry.get('transcription', 'Unknown Command')}"
        except IndexError:
            return "Execute command from history"

    def execute(self, context):
        try:
            # Retrieve the specific command entry using the index
            entry = list(command_history)[self.history_index]
            script_to_execute = entry.get('script')
            original_transcription = entry.get('transcription', 'Unknown Command (Re-run)')

            if not script_to_execute:
                self.report({'WARNING'}, "No script associated with this history item.")
                return {'CANCELLED'}

            update_console(context, f"Re-executing script for: {original_transcription}")
            logger.info(f"Re-executing script from history (index {self.history_index}): {original_transcription}")

            status = 'Unknown'
            try:
                exec(script_to_execute, {"bpy": bpy})
                status = 'Success (Re-run)'
                update_console(context, "Script re-executed successfully.")
            except Exception as e:
                status = 'Script Error (Re-run)'
                ui_error_msg = f"Script Re-execution Error: {str(e)}"
                logger.error(ui_error_msg, exc_info=True)
                update_console(context, ui_error_msg)
                self.report({'ERROR'}, ui_error_msg) # Report error to user

            # Optionally add a new history entry for the re-run attempt
            # This prevents modifying the original entry's status
            new_entry = {
                'transcription': f"{original_transcription} (Re-run)",
                'status': status,
                'script': script_to_execute, # Store script again for potential further re-runs
                'timestamp': time.time()
            }
            command_history.append(new_entry)
            logger.debug(f"Appended re-run attempt to command_history: {new_entry}")

            # Force UI redraw
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()

            return {'FINISHED'}

        except IndexError:
            self.report({'ERROR'}, f"Invalid history index: {self.history_index}")
            return {'CANCELLED'}
        except Exception as e:
            error_msg = f"Error re-executing history command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}


# Operator to initiate editing a history command
class BLENDER_OT_edit_history_command(bpy.types.Operator):
    bl_idname = "wm.edit_history_command"
    bl_label = "Edit History Command"
    bl_options = {'REGISTER'}

    history_index: bpy.props.IntProperty(name="History Index")

    @classmethod
    def description(cls, context, properties):
        try:
            entry = list(command_history)[properties.history_index]
            return f"Edit and Retry: {entry.get('transcription', 'Unknown Command')}"
        except IndexError:
            return "Edit and Retry command from history"

    def execute(self, context):
        props = context.scene.voice_command_props
        try:
            entry = list(command_history)[self.history_index]
            original_transcription = entry.get('transcription', '')
            # Remove potential "(Re-run)" suffix for editing
            original_transcription = original_transcription.replace(" (Re-run)", "").strip()

            props.editing_history_index = self.history_index
            props.edited_text = original_transcription
            logger.info(f"Started editing history item {self.history_index}: {original_transcription}")
            return {'FINISHED'}
        except IndexError:
            self.report({'ERROR'}, f"Invalid history index for editing: {self.history_index}")
            props.editing_history_index = -1 # Reset editing state
            return {'CANCELLED'}
        except Exception as e:
            error_msg = f"Error initiating history edit: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            props.editing_history_index = -1 # Reset editing state
            return {'CANCELLED'}

# Operator to cancel editing a history command
class BLENDER_OT_cancel_edit_command(bpy.types.Operator):
    bl_idname = "wm.cancel_edit_command"
    bl_label = "Cancel Edit"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.voice_command_props
        props.editing_history_index = -1
        props.edited_text = ""
        logger.info("Cancelled history edit.")
        return {'FINISHED'}

# Operator to send the edited command text
class BLENDER_OT_send_edited_command(bpy.types.Operator):
    bl_idname = "wm.send_edited_command"
    bl_label = "Send Edited Command"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.voice_command_props
        if props.editing_history_index == -1 or not props.edited_text:
            self.report({'WARNING'}, "No command text to send.")
            return {'CANCELLED'}

        try:
            # Import client again just in case
            import blender_voice_client
            if not blender_voice_client.client_socket:
                 self.report({'ERROR'}, "Not connected to voice server. Please start listening first.")
                 return {'CANCELLED'}

            text_to_send = props.edited_text
            logger.info(f"Sending edited text command: {text_to_send}")
            # Use the client function to send the text
            success = blender_voice_client.send_text_command(
                text_to_send,
                lambda msg: process_voice_client_message(context, msg) # Use the same callback
            )

            if success:
                update_console(context, f"Sent edited command: '{text_to_send}'")
                # Reset editing state after sending
                props.editing_history_index = -1
                props.edited_text = ""
                return {'FINISHED'}
            else:
                # Error message should have been handled by the callback via send_text_command
                self.report({'ERROR'}, "Failed to send edited command. Check logs.")
                # Optionally reset state here too? Or leave it for user to cancel?
                # props.editing_history_index = -1
                # props.edited_text = ""
                return {'CANCELLED'}

        except ImportError:
            self.report({'ERROR'}, "Failed to import blender_voice_client.")
            return {'CANCELLED'}
        except Exception as e:
            error_msg = f"Error sending edited command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}


# Operator to delete a command from history
class BLENDER_OT_delete_history_command(bpy.types.Operator):
    bl_idname = "wm.delete_history_command"
    bl_label = "Delete History Command"
    bl_options = {'REGISTER'} # No undo needed for simple deletion

    history_index: bpy.props.IntProperty(name="History Index")

    @classmethod
    def description(cls, context, properties):
        # Provide dynamic description based on the command
        try:
            # Need to access the deque carefully
            temp_list = list(command_history)
            if 0 <= properties.history_index < len(temp_list):
                 entry = temp_list[properties.history_index]
                 return f"Delete: {entry.get('transcription', 'Unknown Command')}"
            else:
                 return "Delete command from history (Invalid Index)"
        except Exception: # Catch potential errors during description generation
            return "Delete command from history"

    def execute(self, context):
        global command_history # Ensure we modify the global deque
        try:
            # Convert deque to list for safe indexed deletion
            history_list = list(command_history)

            if 0 <= self.history_index < len(history_list):
                removed_entry = history_list.pop(self.history_index)
                logger.info(f"Removing history item at index {self.history_index}: {removed_entry.get('transcription', 'N/A')}")

                # Recreate the deque from the modified list
                # Important: Keep the maxlen constraint
                new_history = collections.deque(history_list, maxlen=command_history.maxlen)
                command_history = new_history # Replace the global deque

                # Force UI redraw
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            for region in area.regions:
                                if region.type == 'UI':
                                    region.tag_redraw()
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, f"Invalid history index for deletion: {self.history_index}")
                return {'CANCELLED'}

        except Exception as e:
            error_msg = f"Error deleting history command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}


# Panel to display voice command UI
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
        console_box.prop(props, "console_output")
        console_box.prop(props, "selected_model")
        
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
        # Use the 'show_history' property for the toggle arrow
        row.prop(props, "show_history", text="Command History", icon="TIME", emboss=False)

        # Only draw the history content if show_history is True
        if props.show_history:
            # Log current history state before drawing
            logger.debug(f"Drawing history panel. Current history (deque): {list(command_history)}")

            if not command_history:
             history_box.label(text="No commands yet.")
        else:
            # Display last 5 entries (newest first)
            display_list = list(command_history)[-5:]
            logger.debug(f"Displaying last {len(display_list)} history entries.")
            # Iterate through the reversed list to show newest first
            for i, entry in enumerate(reversed(display_list)):
                row = history_box.row(align=True) # Align elements in the row
                status = entry.get('status', 'Unknown')
                transcription = entry.get('transcription', 'N/A')
                script = entry.get('script')
                # Calculate the original index in the full deque
                original_index = len(command_history) - 1 - i

                status_icon = "CHECKMARK" if 'Success' in status else \
                              "ERROR" if 'Error' in status or 'Failed' in status else \
                              "INFO"

                # If there's a script, make it an operator button
                if script:
                    op = row.operator("wm.execute_history_command", text=f"{transcription}", icon=status_icon)
                    op.history_index = original_index
                    # Add status text next to the button if needed
                    row.label(text=f"({status})")
                    # Add delete button
                    del_op = row.operator("wm.delete_history_command", text="", icon='TRASH')
                    del_op.history_index = original_index
                else:
                    # If no script (e.g., failed transcription), just display as label
                    # Use a split layout to add the delete button even for non-executable items
                    split = row.split(factor=0.9) # Adjust factor as needed
                    split.label(text=f"{transcription} ({status})", icon=status_icon)
                    del_op = split.operator("wm.delete_history_command", text="", icon='TRASH')
                    del_op.history_index = original_index
                # Add retry button next to delete button
                retry_op = row.operator("wm.edit_history_command", text="", icon='SHADERFX')
                retry_op.history_index = original_index

                # --- Draw Edit UI Conditionally ---
                if props.editing_history_index == original_index:
                    edit_box = history_box.box() # Use a sub-box for the edit UI
                    edit_box.prop(props, "edited_text", text="") # Show the text box
                    edit_row = edit_box.row(align=True)
                    # Send Button
                    send_op = edit_row.operator("wm.send_edited_command", text="Send to Gemini", icon="PLAY")
                    # Cancel Button
                    cancel_op = edit_row.operator("wm.cancel_edit_command", text="Cancel", icon="CANCEL")


            # Add a button to clear the entire history maybe?
            # clear_row = history_box.row()
            # clear_row.operator("wm.clear_history", text="Clear History", icon="CANCEL")


# Classes to register
classes = (
    VoiceCommandProperties,
    BLENDER_OT_voice_command,
    BLENDER_OT_stop_voice_command,
    BLENDER_OT_execute_history_command,
    BLENDER_OT_delete_history_command,
    BLENDER_OT_edit_history_command,     # Register new operators
    BLENDER_OT_cancel_edit_command,
    BLENDER_OT_send_edited_command,
    BLENDER_PT_voice_command_panel,
)

def register():
    try:
        # Register classes
        for cls in classes:
            bpy.utils.register_class(cls)
        
        # Register properties
        bpy.types.Scene.voice_command_props = bpy.props.PointerProperty(type=VoiceCommandProperties)
        
        # Try to load API key from .env file
        try:
            env_path = Path(__file__).parent / '.env'
            if env_path.exists():
                with open(env_path, 'r') as file:
                    content = file.read()
                    match = re.search(r'GEMINI_API_KEY=([^\n\r]*)', content)
                    if match and match.group(1) and match.group(1) != 'your_gemini_api_key_here':
                        # Set the API key in the properties
                        # Use a safer approach to access scenes
                        try:
                            # Check if we can access the current scene
                            if hasattr(bpy.context, 'scene'):
                                bpy.context.scene.voice_command_props.api_key = match.group(1)
                            # Otherwise try to access all scenes if available
                            elif hasattr(bpy.data, 'scenes') and bpy.data.scenes:
                                for scene in bpy.data.scenes:
                                    scene.voice_command_props.api_key = match.group(1)
                        except AttributeError:
                            # If we can't access scenes now, the API key will still be in .env
                            # and will be loaded when the addon is fully initialized
                            logger.warning("Could not set API key to scenes - will be loaded from .env when needed")
        except Exception as env_error:
            logger.error(f"Error loading API key from .env: {str(env_error)}", exc_info=True)
        
        logger.info("Articulate 3D Add-on registered successfully!")
    except Exception as e:
        logger.critical(f"Error registering Articulate 3D Add-on: {str(e)}", exc_info=True)

def unregister():
    try:
        # Unregister classes in reverse order
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        
        # Remove properties
        del bpy.types.Scene.voice_command_props
        logger.info("Articulate 3D Add-on unregistered.")
    except Exception as e:
        logger.error(f"Error unregistering Articulate 3D Add-on: {str(e)}", exc_info=True)

if __name__ == "__main__":
    register()
