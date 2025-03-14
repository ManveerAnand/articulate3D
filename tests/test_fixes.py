import sys
import os
from pathlib import Path

# Add the addon directory to the path
addon_dir = Path(__file__).parent
if str(addon_dir) not in sys.path:
    sys.path.insert(0, str(addon_dir))

# Test blender_voice_client.py fix
print("Testing blender_voice_client.py fix...")
import blender_voice_client

# Test the stop_flag functionality
print(f"stop_flag type: {type(blender_voice_client.stop_flag)}")
print("Setting stop_flag...")
blender_voice_client.stop_flag.set()
print("Clearing stop_flag...")
blender_voice_client.stop_flag.clear()
print("stop_flag test passed successfully!")

# Note: We can't fully test the __init__.py fix without Blender,
# but we can verify the module imports correctly
print("\nTesting __init__.py imports...")
try:
    import __init__
    print("Successfully imported __init__.py")
except Exception as e:
    print(f"Error importing __init__.py: {e}")
    
print("\nAll tests completed!")