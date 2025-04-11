import sys
from unittest.mock import MagicMock

# Create a mock object for the bpy module
bpy_mock = MagicMock()

# Add the mock bpy module to sys.modules.
# This ensures that any subsequent 'import bpy' statements
# will import our mock object instead of raising an ImportError.
# This needs to happen before pytest tries to import any test files
# that might indirectly cause __init__.py (which imports bpy) to be loaded.
sys.modules['bpy'] = bpy_mock
sys.modules['bpy.ops'] = MagicMock()
sys.modules['bpy.types'] = MagicMock()
sys.modules['bpy.utils'] = MagicMock()
sys.modules['bpy.props'] = MagicMock()
# Add other submodules if needed by the code being imported during test collection

print("Mocking bpy module for pytest session.")

# You can also define fixtures here if needed later
