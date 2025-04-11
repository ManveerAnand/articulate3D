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
            logger.info(f"Attempting to execute script:\n---\n{script_to_execute}\n---")
            logger.info(f"Context before exec: area={context.area.type if context.area else 'None'}, window={context.window.screen.name if context.window else 'None'}, mode={context.mode if hasattr(context, 'mode') else 'N/A'}")
            update_console(context, f"Executing script for: {transcription or 'Unknown command'}")
            exec(script_to_execute, {"bpy": bpy})
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
        
        # ... (API Config, Status, Console, Command Buttons, Help - remain the same) ...
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
        # ... (rest of register remains the same) ...
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
