import os
import sys
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print(f'Current directory: {os.path.dirname(os.path.abspath(__file__))}')
print(f'Python version: {sys.version}')

# Try to import speech recognition
try:
    import speech_recognition as sr
    print('Successfully imported speech_recognition')
    
    # List available microphones
    print('\nAvailable microphones:')
    mic_list = sr.Microphone.list_microphone_names()
    for i, mic_name in enumerate(mic_list):
        print(f'{i}: {mic_name}')
    
    # Try to use the default microphone
    print('\nTesting default microphone...')
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print('Microphone initialized successfully')
            print('Adjusting for ambient noise... Please wait.')
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print('Ready to listen. Say something...')
            
            # Listen for audio
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
                print('Audio captured successfully!')
                
                # Try to transcribe
                try:
                    text = recognizer.recognize_google(audio)
                    print(f'Transcribed: "{text}"')
                except sr.UnknownValueError:
                    print('Could not understand audio')
                except sr.RequestError as e:
                    print(f'Could not request results; {e}')
            except sr.WaitTimeoutError:
                print('No audio detected within timeout period')
            except Exception as e:
                print(f'Error during listening: {e}')
    except Exception as e:
        print(f'Error initializing microphone: {e}')
        print('\nTroubleshooting tips:')
        print('1. Make sure your microphone is properly connected')
        print('2. Check system permissions for microphone access')
        print('3. Try selecting a specific microphone index instead of default')
        
        # Try with specific microphone if available
        if len(mic_list) > 0:
            print('\nTrying with specific microphone...')
            try:
                with sr.Microphone(device_index=0) as source:
                    print(f'Successfully initialized microphone: {mic_list[0]}')
            except Exception as e:
                print(f'Error with specific microphone: {e}')
                
except ImportError as e:
    print(f'Import error: {e}')
    print('Please run setup.py to install required dependencies')

print('\nTest completed')