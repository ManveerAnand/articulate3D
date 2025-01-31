import speech_recognition as sr
import requests
import json
import tempfile
import os

GOOGLE_API_KEY = "AIzaSyC38YOMuw5v4WG4JHo0wUZSgq2tXNZ7hgA"

def generate_blender_script(command, model="gemini-2.0-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GOOGLE_API_KEY
    }
    data = {
        "contents": [{
            "parts":[{
                "text": f"Convert this command to Blender Python code: {command}"
            }]
        }]
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text']
    return None

def listen_and_process():
    recognizer = sr.Recognizer()
    
    with sr.Microphone() as source:
        print("Listening for command...")
        audio = recognizer.listen(source)
        
    try:
        command = recognizer.recognize_google(audio)
        print(f"Command received: {command}")
        
        script = generate_blender_script(command)
        if script:
            # Save the script to a temporary file that Blender can read
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                f.write(script)
            print(f"Script saved to: {f.name}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    listen_and_process() 