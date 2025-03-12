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
            # Import voice server module directly to avoid relative import issues
            import sys
            import os
            # Add the addon directory to the path to ensure proper imports
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            if addon_dir not in sys.path:
                sys.path.insert(0, addon_dir)
            
            # Now import the voice_server module
            import voice_server
            
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
            
            # Start voice recognition in a separate process
            voice_server.start_listening(
                api_key=props.api_key,
                model=props.selected_model,
                callback=lambda msg: update_console(context, msg)
            )
            
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
            # Import voice server module directly to avoid relative import issues
            import sys
            import os
            # Add the addon directory to the path to ensure proper imports
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            if addon_dir not in sys.path:
                sys.path.insert(0, addon_dir)
            
            # Now import the voice_server module
            import voice_server
            
            # Stop the voice recognition
            update_console(context, "Stopping voice recognition...")
            voice_server.stop_listening(lambda msg: update_console(context, msg))
            
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
                        for scene in bpy.data.scenes:
                            scene.voice_command_props.api_key = match.group(1)
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