import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print(f'Current directory: {os.path.dirname(os.path.abspath(__file__))}')
print(f'Python version: {sys.version}')
print(f'Python path: {sys.path}')

try:
    # Try to import the voice_server module
    import voice_server
    print('Successfully imported voice_server')
    
    # Check if stop_listening function exists
    has_stop_listening = hasattr(voice_server, 'stop_listening')
    print(f'Has stop_listening: {has_stop_listening}')
    
    # Print all available attributes in voice_server
    print('\nAvailable attributes in voice_server:')
    for attr in dir(voice_server):
        if not attr.startswith('__'):
            print(f'- {attr}')
            
except Exception as e:
    print(f'Import error: {e}')