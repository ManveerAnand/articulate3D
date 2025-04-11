bl_info = {
    "name": "Sample Test Addon",
    "author": "Test",
    "version": (1, 0),
    "blender": (4, 0, 0), # Match your Blender version if different
    "location": "View3D > Sidebar > Sample Tab",
    "description": "Minimal addon to test script path loading",
    "category": "Testing",
}

import bpy

class SAMPLE_PT_Panel(bpy.types.Panel):
    bl_label = "Sample Panel"
    bl_idname = "SAMPLE_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Sample Tab'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Sample Addon Loaded!")

def register():
    print("Registering Sample Test Addon")
    bpy.utils.register_class(SAMPLE_PT_Panel)
    print("Sample Test Addon Registered")

def unregister():
    print("Unregistering Sample Test Addon")
    bpy.utils.unregister_class(SAMPLE_PT_Panel)
    print("Sample Test Addon Unregistered")

if __name__ == "__main__":
