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
from pathlib import Path

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

# Function to update console output
def update_console(context, text):
    props = context.scene.voice_command_props
    props.console_output = text
    print(text)

# Function to handle received scripts
def handle_script(context, script):
    """Handle a script received from the voice recognition server"""
    try:
        # Add the script to the execution queue
        script_queue.append(script)
        update_console(context, f"Received script to execute")
    except Exception as e:
        update_console(context, f"Error handling script: {str(e)}")

# Function to process messages from the voice client
def process_voice_client_message(context, message):
    """Process messages from the voice client"""
    try:
        # If it's a string, just update the console
        if isinstance(message, str):
            update_console(context, message)
        # If it's a dict with a script, handle the script
        elif isinstance(message, dict) and "script" in message:
            handle_script(context, message["script"])
            update_console(context, message.get("message", "Script received"))
        # Otherwise, just convert to string and update console
        else:
            update_console(context, str(message))
    except Exception as e:
        update_console(context, f"Error processing message: {str(e)}")

# Timer function to execute scripts from the queue
def execute_scripts_timer():
    """Timer function to execute scripts from the queue"""
    context = bpy.context
    
    # Check if there are any scripts in the queue
    if script_queue:
        # Get the next script
        script = script_queue.pop(0)
        
        try:
            # Execute the script
            update_console(context, "Executing script...")
            exec(script, {"bpy": bpy})
            update_console(context, "Script executed successfully")
        except Exception as e:
            update_console(context, f"Error executing script: {str(e)}")
    
    # Return True to keep the timer running
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
                error_msg = response.json().get('error', {}).get('message', 'Unknown error')
                print(f"API key validation error: {error_msg} (Status code: {response.status_code})")
                return False
        except Exception as e:
            print(f"API key validation error: {str(e)}")
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
                self.report({'ERROR'}, "Invalid API key. Please check your Gemini API key.")
                update_console(context, "API key validation failed. Please check your key.")
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
                self.report({'ERROR'}, "Failed to start voice recognition client")
                props.is_listening = False
                return {'CANCELLED'}
            
            # Start the timer to execute scripts
            bpy.app.timers.register(execute_scripts_timer)
            
            return {'FINISHED'}
        except Exception as e:
            props.is_listening = False
            error_msg = f"Error: {str(e)}"
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
        except Exception as e:
            error_msg = f"Error stopping voice recognition: {str(e)}"
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            # Still reset the listening state
            props.is_listening = False
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

# Classes to register
classes = (
    VoiceCommandProperties,
    BLENDER_OT_voice_command,
    BLENDER_OT_stop_voice_command,
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
                            print("Could not set API key to scenes - will be loaded from .env when needed")
        except Exception as env_error:
            print(f"Error loading API key from .env: {str(env_error)}")
        
        print("Articulate 3D Add-on registered successfully!")
    except Exception as e:
        print(f"Error registering Articulate 3D Add-on: {str(e)}")

def unregister():
    try:
        # Unregister classes in reverse order
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        
        # Remove properties
        del bpy.types.Scene.voice_command_props
    except Exception as e:
        print(f"Error unregistering Articulate 3D Add-on: {str(e)}")

if __name__ == "__main__":
    register()