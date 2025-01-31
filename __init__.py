bl_info = {
    "name": "Voice Command for Blender",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Voice",
    "description": "Control Blender using voice commands with Gemini AI",
    "category": "3D View",
}

import bpy  
import os
import json
import requests
from pathlib import Path

# Addon core functionality
class VoiceCommandProperties(bpy.types.PropertyGroup):
    is_listening: bpy.props.BoolProperty(
        name="Is Listening",
        default=False
    )
    api_key: bpy.props.StringProperty(
        name="API Key",
        description="Your Google Gemini API Key",
        default="",
        subtype='PASSWORD'  # This will show as dots for security
    )
    selected_model: bpy.props.EnumProperty(
        items=[
            ('gemini-2.0-flash', "Gemini 2.0 Flash", "Latest experimental flash model"),
            ('gemini-1.5-flash', "Gemini 1.5 Flash", "Latest stable flash model"),
        ],
        name="Gemini Model",
        default='gemini-2.0-flash'
    )
    console_output: bpy.props.StringProperty(
        name="Console Output",
        default="Ready...",
        maxlen=1024
    )

def update_console(context, text):
    props = context.scene.voice_command_props
    props.console_output = text
    print(text)  # Also print to system console

class BLENDER_OT_voice_command(bpy.types.Operator):
    bl_idname = "wm.voice_command"
    bl_label = "Voice Command"
    
    def execute(self, context):
        props = context.scene.voice_command_props
        
        if not props.api_key:
            self.report({'ERROR'}, "Please enter your Gemini API key first")
            return {'CANCELLED'}
            
        try:
            from . import voice_server
            props.is_listening = True
            update_console(context, "Starting voice recognition...")
            
            # Pass the API key to the voice server
            voice_server.start_listening(api_key=props.api_key, 
                                      model=props.selected_model,
                                      callback=lambda msg: update_console(context, msg))
            return {'FINISHED'}
        except Exception as e:
            props.is_listening = False
            error_msg = f"Error: {str(e)}"
            update_console(context, error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

class BLENDER_PT_voice_command_panel(bpy.types.Panel):
    bl_label = "Voice Command Panel"
    bl_idname = "BLENDER_PT_voice_command"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Voice'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.voice_command_props
        
        # API Key input
        api_box = layout.box()
        api_box.label(text="Configuration:", icon='SETTINGS')
        api_box.prop(props, "api_key")
        
        # Status indicator
        status_box = layout.box()
        status_row = status_box.row()
        status_row.label(text="Status:")
        if props.is_listening:
            status_row.label(text="Listening...", icon='RADIOBUT_ON')
        else:
            status_row.label(text="Ready", icon='RADIOBUT_OFF')
        
        # Console output
        console_box = layout.box()
        console_box.label(text="Console Output:", icon='CONSOLE')
        console_box.label(text=props.console_output)
        
        # Model selection
        layout.prop(props, "selected_model")
        
        # Command button
        cmd_row = layout.row()
        cmd_row.enabled = bool(props.api_key)  # Disable if no API key
        cmd_row.scale_y = 2.0
        op = cmd_row.operator("wm.voice_command", 
                            text="Start Voice Command", 
                            icon='REC')
        
        if not props.api_key:
            layout.label(text="⚠️ Please enter API key first", icon='ERROR')
        
        # Help box
        help_box = layout.box()
        help_box.label(text="Voice Command Examples:", icon='QUESTION')
        help_box.label(text="• Create a red cube")
        help_box.label(text="• Add a smooth sphere")
        help_box.label(text="• Move object up 2 units")

classes = (
    VoiceCommandProperties,
    BLENDER_OT_voice_command,
    BLENDER_PT_voice_command_panel,
)

def register():
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.types.Scene.voice_command_props = bpy.props.PointerProperty(type=VoiceCommandProperties)
        print("Voice Command Add-on registered successfully!")
    except Exception as e:
        print(f"Error registering Voice Command Add-on: {str(e)}")

def unregister():
    try:
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        del bpy.types.Scene.voice_command_props
    except Exception as e:
        print(f"Error unregistering Voice Command Add-on: {str(e)}")

if __name__ == "__main__":
    register() 