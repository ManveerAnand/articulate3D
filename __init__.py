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
            ("gemini-2.0-flash", "Gemini 2.0 Flash", "Fast model"),
            ("gemini-2.0-pro", "Gemini 2.0 Pro", "Advanced model"),
            ("gemini-2.0-thinking", "Gemini 2.0 Thinking", "Complex reasoning"),
            ("gemini-1.5-flash", "Gemini 1.5 Flash", "Stable flash")
        ], name="Gemini Model", default="gemini-2.0-flash"
    )
    console_output: bpy.props.StringProperty(name="Console Output", default="Ready...", maxlen=1024)
    show_history: bpy.props.BoolProperty(name="Show Command History", default=True)
    show_starred: bpy.props.BoolProperty(name="Show Starred Commands", default=False)
    edit_script: bpy.props.BoolProperty(
        name="Edit Script",
        description="Open generated script in text editor for modification",
        default=False
    )

# --- Core Functions ---
def update_console(context, text):
    props = context.scene.voice_command_props
    props.console_output = text
    logger.info(text)

def handle_script(context, script):
    """Handle a script received from the voice recognition server"""
    try:
        # Store the script in a text block named "Generated Script"
        text_name = "Generated Script"
        if text_name not in bpy.data.texts:
            text = bpy.data.texts.new(text_name)
        else:
            text = bpy.data.texts[text_name]
        
        # Clear and set the new script
        text.clear()
        text.write(script)
        
        # If edit_script is False, execute immediately
        props = context.scene.voice_command_props
        if not props.edit_script:
            try:
                exec(script)
                update_console(context, "Script executed successfully")
            except Exception as e:
                update_console(context, f"Error executing script: {str(e)}")
                logger.error(f"Error executing script: {str(e)}", exc_info=True)
        else:
            update_console(context, "Script stored in text editor. Click 'Execute Script' to run it.")
        
        return True
    except Exception as e:
        update_console(context, f"Error handling script: {str(e)}")
        logger.error(f"Error handling script: {str(e)}", exc_info=True)
        return False

def process_voice_client_message(context, message):
    global last_transcription, command_history
    try:
        logger.debug(f"Processing message: {message}")
        if isinstance(message, str):
            update_console(context, message)
        elif isinstance(message, dict):
            status = message.get("status", "unknown")
            msg_text = message.get("message", "No message content.")

            if status == "transcribed":
                last_transcription = msg_text.replace("Transcribed: ", "").strip()
                update_console(context, f"Server: {msg_text}")
            elif status == "script":
                script_content = message.get("script", "")
                original_text = message.get("original_text") # Text from edited command
                command_text = original_text if original_text else last_transcription

                if command_text:
                    script_queue.append((script_content, command_text))
                    update_console(context, f"Received script for '{command_text}' - queued.")
                    if not original_text: # Clear only if it was from voice
                        last_transcription = None
                else:
                    logger.warning("Received script message without associated command text.")
                    script_queue.append((script_content, None)) # Queue anyway
                    update_console(context, "Received script (unknown origin) - queued.")

            elif status == "error":
                logger.error(f"Received error from server: {msg_text}")
                update_console(context, f"Server Error: {msg_text}")
                if last_transcription: # Log error against last voice command attempt
                     entry = {
                        'transcription': last_transcription, 'status': 'Failed Generation/STT',
                        'script': None, 'timestamp': time.time(), 'starred': False
                     }
                     command_history.append(entry)
                     last_transcription = None
                else:
                    logger.warning("Received error message but last_transcription was None.")
            elif status in ["info", "ready", "stopped"]:
                 logger.debug(f"Received status '{status}' message.")
                 update_console(context, f"Server: {msg_text}")
            else:
                logger.warning(f"Received message with unhandled status: {status}")
                update_console(context, f"Server: {msg_text}")
        else:
            logger.warning(f"Received unexpected message format: {type(message)} - {message}")
            update_console(context, str(message))
    except Exception as e:
        ui_error_msg = f"Error processing message from server: {str(e)}"
        logger.error(ui_error_msg, exc_info=True)
        update_console(context, ui_error_msg)

def execute_scripts_timer():
    global command_history
    context = bpy.context
    needs_redraw = False
    if script_queue:
        script_to_execute, transcription = script_queue.pop(0)
        logger.debug(f"Dequeued script for transcription: {transcription}")
        status = 'Unknown'
        entry_timestamp = time.time() # Use consistent timestamp
        try:
            # Store the script in a text block
            text_name = "Generated Script"
            if text_name not in bpy.data.texts:
                text = bpy.data.texts.new(text_name)
            else:
                text = bpy.data.texts[text_name]
            
            # Clear and set the new script
            text.clear()
            text.write(script_to_execute)
            
            logger.info(f"Attempting to execute script:\n---\n{script_to_execute}\n---")
            logger.info(f"Context before exec: area={context.area.type if context.area else 'None'}, window={context.window.screen.name if context.window else 'None'}, mode={context.mode if hasattr(context, 'mode') else 'N/A'}")
            update_console(context, f"Executing script for: {transcription or 'Unknown command'}")
            
            # Create a custom namespace that includes bpy and our update_console function
            namespace = {
                "bpy": bpy,
                "update_console": lambda msg: update_console(context, msg)
            }
            
            # Execute the script with our custom namespace
            exec(script_to_execute, namespace)
            
            status = 'Success'
            update_console(context, "Script executed successfully.")
        except Exception as e:
            status = 'Script Error'
            ui_error_msg = f"Script Execution Error: {str(e)}"
            logger.error(ui_error_msg, exc_info=True)
            update_console(context, ui_error_msg)
        
        if transcription:
             entry = {
                 'transcription': transcription, 'status': status,
                 'script': script_to_execute, 'timestamp': entry_timestamp,
                 'starred': False # New entries are never starred by default
             }
             command_history.append(entry)
             logger.debug(f"Appended to command_history: {entry}")
             needs_redraw = True
        else:
              logger.warning("Script executed, but no transcription was associated.")
              
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
    # ... (validate_api_key remains the same) ...
    def validate_api_key(self, api_key):
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
            if not bpy.app.timers.is_registered(execute_scripts_timer):
                bpy.app.timers.register(execute_scripts_timer)
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

            if not script_to_execute:
                self.report({'WARNING'}, "No script associated with this item.")
                return {'CANCELLED'}

            update_console(context, f"Executing {'starred' if self.is_starred_execution else 'history'} command: {original_transcription}")
            logger.info(f"Executing {'starred' if self.is_starred_execution else 'history'} script (index {self.history_index}): {original_transcription}")

            status = 'Unknown'
            try:
                exec(script_to_execute, {"bpy": bpy})
                status = 'Success (Executed)'
                update_console(context, "Script executed successfully.")
            except Exception as e:
                status = 'Script Error (Executed)'
                ui_error_msg = f"Script Execution Error: {str(e)}"
                logger.error(ui_error_msg, exc_info=True)
                update_console(context, ui_error_msg)
                self.report({'ERROR'}, ui_error_msg)

            # Add a NEW entry to the main history, always unstarred
            new_entry = {
                'transcription': f"{original_transcription} (Executed)",
                'status': status,
                'script': script_to_execute,
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

class BLENDER_OT_run_script(bpy.types.Operator):
    bl_idname = "wm.run_script"
    bl_label = "Run Script"
    bl_description = "Execute the script in the text editor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.voice_command_props
        script = props.script_text
        
        if not script.strip():
            self.report({'WARNING'}, "No script to execute")
            return {'CANCELLED'}
        
        try:
            # Execute the script
            exec(script)
            self.report({'INFO'}, "Script executed successfully")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error executing script: {str(e)}")
            return {'CANCELLED'}

class BLENDER_OT_open_stored_script(bpy.types.Operator):
    bl_idname = "wm.open_stored_script"
    bl_label = "Edit Last Script"
    bl_description = "Open the last executed script in the text editor"
    
    def execute(self, context):
        try:
            # Find a text editor
            text_editor = None
            for area in context.screen.areas:
                if area.type == 'TEXT_EDITOR':
                    text_editor = area
                    break
            
            if text_editor is None:
                # No text editor found, create one by splitting the current area
                current_area = context.area
                bpy.ops.screen.area_split(direction='VERTICAL', factor=0.3)
                
                # The new area is always the last one in the areas list
                text_editor = context.screen.areas[-1]
                text_editor.type = 'TEXT_EDITOR'
            
            # Find the text block
            text_name = "Generated Script"
            if text_name not in bpy.data.texts:
                self.report({'ERROR'}, "No script found to edit")
                return {'CANCELLED'}
            
            text = bpy.data.texts[text_name]
            
            # Set the text block as active
            text_editor.spaces.active.text = text
            
            # Set cursor position and selection
            text.cursor_set(0)
            
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error opening script: {str(e)}")
            return {'CANCELLED'}

class BLENDER_OT_execute_text_script(bpy.types.Operator):
    bl_idname = "wm.execute_text_script"
    bl_label = "Execute Script"
    bl_description = "Execute the current script in the text editor"
    
    def execute(self, context):
        try:
            text_name = "Generated Script"
            if text_name not in bpy.data.texts:
                self.report({'ERROR'}, "No script found in text editor")
                return {'CANCELLED'}
            
            text = bpy.data.texts[text_name]
            script = text.as_string()
            
            if not script.strip():
                self.report({'WARNING'}, "No script to execute")
                return {'CANCELLED'}
            
            # Create namespace with access to bpy and update_console
            namespace = {
                "bpy": bpy,
                "update_console": lambda msg: update_console(context, msg)
            }
            
            # Execute the script with our namespace
            exec(script, namespace)
            update_console(context, "Script executed successfully")
            self.report({'INFO'}, "Script executed successfully")
            return {'FINISHED'}
        except Exception as e:
            error_msg = f"Error executing script: {str(e)}"
            update_console(context, error_msg)
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
        
        # API Key and Model Selection
        box = layout.box()
        box.label(text="Configuration")
        box.prop(props, "api_key")
        box.prop(props, "selected_model")
        
        # Voice Control Buttons
        box = layout.box()
        box.label(text="Voice Control")
        row = box.row()
        if not props.is_listening:
            row.operator("wm.voice_command", text="Start Listening", icon='PLAY')
        else:
            row.operator("wm.stop_voice_command", text="Stop Listening", icon='PAUSE')
        
        # Console Output
        box = layout.box()
        box.label(text="Console")
        box.prop(props, "console_output", text="")
        
        # Script Options
        box = layout.box()
        box.label(text="Script Options", icon='TEXT')
        
        # Edit script option
        box.prop(props, "edit_script", text="Edit Script Before Execution")
        
        # Edit last script button
        edit_row = box.row()
        edit_btn = edit_row.operator("wm.open_stored_script", text="Edit Last Script", icon="TEXT")
        edit_row.enabled = "Generated Script" in bpy.data.texts
        
        # Execute script button
        execute_row = box.row()
        execute_btn = execute_row.operator("wm.execute_text_script", text="Execute Script", icon="PLAY")
        execute_row.enabled = "Generated Script" in bpy.data.texts
        
        # History Section
        box = layout.box()
        row = box.row()
        row.prop(props, "show_history", text="Command History", icon='TIME')
        
        if props.show_history:
            for i, entry in enumerate(command_history):
                row = box.row()
                if entry.get('starred'):
                    row.operator("wm.toggle_star_history_command", text="", icon='SOLO_ON', emboss=False).history_index = i
                else:
                    row.operator("wm.toggle_star_history_command", text="", icon='SOLO_OFF', emboss=False).history_index = i
                
                row.operator("wm.execute_history_command", text=entry.get('transcription', 'Unknown')).history_index = i
                row.operator("wm.delete_history_command", text="", icon='X', emboss=False).history_index = i
        
        # Starred Commands Section
        box = layout.box()
        row = box.row()
        row.prop(props, "show_starred", text="Starred Commands", icon='SOLO_ON')
        
        if props.show_starred and starred_commands:
            for i, entry in enumerate(starred_commands):
                row = box.row()
                row.operator("wm.execute_history_command", text=entry.get('transcription', 'Unknown')).history_index = i
                row.operator("wm.delete_history_command", text="", icon='X', emboss=False).history_index = i

# --- Registration ---
classes = (
    VoiceCommandProperties,
    BLENDER_OT_voice_command,
    BLENDER_OT_stop_voice_command,
    BLENDER_OT_execute_history_command,
    BLENDER_OT_toggle_star_history_command, # Register star operator
    BLENDER_OT_delete_history_command,
    BLENDER_OT_run_script,
    BLENDER_OT_open_stored_script,
    BLENDER_OT_execute_text_script,
    BLENDER_PT_voice_command_panel,
)

def register():
    bpy.utils.register_class(VoiceCommandProperties)
    bpy.types.Scene.voice_command_props = bpy.props.PointerProperty(type=VoiceCommandProperties)
    
    bpy.utils.register_class(BLENDER_OT_voice_command)
    bpy.utils.register_class(BLENDER_OT_stop_voice_command)
    bpy.utils.register_class(BLENDER_OT_execute_history_command)
    bpy.utils.register_class(BLENDER_OT_toggle_star_history_command)
    bpy.utils.register_class(BLENDER_OT_delete_history_command)
    bpy.utils.register_class(BLENDER_OT_run_script)
    bpy.utils.register_class(BLENDER_OT_open_stored_script)
    bpy.utils.register_class(BLENDER_OT_execute_text_script)
    bpy.utils.register_class(BLENDER_PT_voice_command_panel)
    
    # Start the script execution timer
    bpy.app.timers.register(execute_scripts_timer, persistent=True)
    
    logger.info("Articulate 3D Add-on registered successfully!")

def unregister():
    # Stop the script execution timer
    bpy.app.timers.unregister(execute_scripts_timer)
    
    bpy.utils.unregister_class(BLENDER_PT_voice_command_panel)
    bpy.utils.unregister_class(BLENDER_OT_run_script)
    bpy.utils.unregister_class(BLENDER_OT_delete_history_command)
    bpy.utils.unregister_class(BLENDER_OT_toggle_star_history_command)
    bpy.utils.unregister_class(BLENDER_OT_execute_history_command)
    bpy.utils.unregister_class(BLENDER_OT_stop_voice_command)
    bpy.utils.unregister_class(BLENDER_OT_voice_command)
    bpy.utils.unregister_class(BLENDER_OT_open_stored_script)
    bpy.utils.unregister_class(BLENDER_OT_execute_text_script)
    
    del bpy.types.Scene.voice_command_props
    bpy.utils.unregister_class(VoiceCommandProperties)

def create_monkey():
    """Creates a Suzanne monkey mesh object."""
    try:
        # Create the monkey mesh data
        mesh = bpy.data.meshes.new("Monkey_Mesh")
        monkey_object = bpy.data.objects.new("Monkey", mesh)

        # Link the object to the scene
        scene = bpy.context.scene
        scene.collection.link_instance(monkey_object)

        # Generate the Suzanne data
        bpy.ops.mesh.primitive_monkey_add(size=1, enter_editmode=False, align='WORLD', location=(0, 0, 0), rotation=(0, 0, 0))
        
        # Get the newly created monkey object
        new_monkey = bpy.context.active_object

        # Copy the mesh data from the newly created monkey to our monkey object
        monkey_object.data = new_monkey.data

        # Remove the temporary monkey object
        bpy.data.objects.remove(new_monkey, do_unlink=True)

        update_console("Monkey created successfully!")
        return monkey_object

    except Exception as e:
        update_console(f"Error creating monkey: {e}")
        return None

def main():
    """Main function to execute the monkey creation."""
    try:
        monkey = create_monkey()
        if monkey:
            update_console("Monkey creation completed!")
    except Exception as e:
        update_console(f"An error occurred: {e}")

if __name__ == "__main__":
    register()
