Sure — I’ve refactored your entire detailed plan into clean, structured **Markdown** while preserving **all the specifics**:

---

# 🎯 Articulate 3D Addon — Update Plan

## Objective:
- Enable dynamic selection of **Gemini models** (2.0 Flash, 2.5 Pro) from Blender UI.
- Integrate 3 audio processing methods:
    - Direct audio input to Gemini.
    - Transcription via OpenAI Whisper (`base` model) ➡️ Gemini text processing.
    - Transcription via Google Cloud STT ➡️ Gemini text processing.
- Shift audio recording from server ➡️ Blender client.

---

## 📦 Phase 1: Dependencies & Setup (`setup.py`, `.env.example`)

### Modify `setup.py`:
- In `install_dependencies()`:
    - Replace:  
      ```diff
      - "google-generativeai"
      + "google-genai"
      ```
    - Add:
      ```python
      "openai-whisper"
      "google-cloud-speech"
      "sounddevice"  # Recommended for robust client-side audio recording.
      ```
    - After dependency installation, add:
      ```python
      print("\nNote: If using the Whisper method, ensure ffmpeg is installed "
            "(e.g., 'sudo apt install ffmpeg' or 'brew install ffmpeg').")
      ```

### Modify `.env.example`:
- Add:
  ```bash
  GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google_cloud_keyfile.json  # Required for Google Cloud STT method.
  ```

---

### ⚠️ **User Action:**
- Run:
  ```bash
  python setup.py
  ```
- Install **ffmpeg** (`sudo apt install ffmpeg` or `brew install ffmpeg`).
- Set **Google Cloud credentials** for STT.

---

## 🖥️ Phase 2: Server Updates (`src/standalone_voice_server.py`)

### Imports:
- Replace:
  ```python
  import google.generativeai as genai
  ```
  with:
  ```python
  from google import genai
  ```
- Add:
  ```python
  import whisper
  from google.cloud import speech
  import base64
  import io
  import wave
  import tempfile
  import numpy as np
  ```
- Remove:
  ```python
  import speech_recognition as sr
  ```
- Review if **PyAudio** can be removed from dependencies.

---

### Remove Server-Side Recording:
- Delete:
  - `voice_recognition_thread` function.
  - The call to `start voice_thread` in `start_server`.

---

### Refactor Gemini Text Processing:
- Rename:  
  `process_with_gemini` ➡️ `process_text_with_gemini`.
- Modify signature:
  ```python
  def process_text_with_gemini(client, text, model_name, blender_context):
  ```
- Inside:
    - Remove:
      ```python
      genai.configure
      genai.GenerativeModel
      ```
    - Use:
      ```python
      client.models.generate_content(model=f'models/{model_name}', contents=prompt, config=...)
      ```
    - Adapt `generation_config` and `safety_settings` to:
      ```python
      google.genai.types.GenerateContentConfig
      ```
    - Handle `response.text` accordingly.

---

### Add Gemini Audio Processing:
- Define:
  ```python
  def process_audio_with_gemini(client, audio_bytes, model_name, blender_context):
  ```
- Use `client.models.generate_content` with:
  - `genai.types.Blob` and `genai.types.Part`.
  - Correct `audio MIME type` (`audio/wav`).

---

### Add Whisper Transcription:
- Define:
  ```python
  def transcribe_with_whisper(audio_bytes):
  ```
- Steps:
  1. Load model:
      ```python
      model = whisper.load_model("base")
      ```
  2. Write `audio_bytes` to temporary WAV:
      ```python
      tempfile.NamedTemporaryFile
      ```
  3. Transcribe:
      ```python
      result = model.transcribe(temp_file_path)
      ```
  4. Clean up temp file.
  5. Return:
      ```python
      result['text']
      ```

---

### Add Google Cloud STT Transcription:
- Define:
  ```python
  def transcribe_with_google_stt(audio_bytes):
  ```
- Steps:
  1. Initialize:
      ```python
      client = speech.SpeechClient()
      ```
  2. Prepare `RecognitionAudio`:
      ```python
      audio = speech.RecognitionAudio(content=audio_bytes)
      ```
  3. Prepare `RecognitionConfig`:
      ```python
      config = speech.RecognitionConfig(
          encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
          sample_rate_hertz=16000,
          language_code="en-US"
      )
      ```
  4. Transcribe:
      ```python
      response = client.recognize(config=config, audio=audio)
      ```
  5. Return concatenated result:
      ```python
      "".join(result.alternatives[0].transcript for result in response.results)
      ```

---

### Update `client_message_handler_thread`:
- Initialize:
  ```python
  genai_client = genai.Client(api_key=api_key)
  ```
- Expect messages:
  ```json
  {
    "type": "process_audio",
    "audio_data": "base64string",
    "model": "gemini-...",
    "method": "whisper/google_stt/gemini",
    "context": {...},
    "audio_format": {"sample_rate": 16000, "encoding": "wav"}
  }
  ```
- Decode:
  ```python
  audio_bytes = base64.b64decode(client_message.get("audio_data"))
  ```
- Route based on `method`:
    ```python
    if method == "gemini":
        process_audio_with_gemini(...)
    elif method == "whisper":
        transcribe_with_whisper(...) ➡️ process_text_with_gemini(...)
    elif method == "google_stt":
        transcribe_with_google_stt(...) ➡️ process_text_with_gemini(...)
    ```
- Send response back via:
    ```python
    conn.sendall(json.dumps(...))
    ```

---

### Update `start_server`:
- Remove:
  ```python
  model = os.environ.get(...)
  ```
- Pass only:
  ```python
  api_key
  ```
to `client_message_handler_thread`.

---

## 🧑‍🎨 Phase 3: Client Updates (`blender_voice_client.py`, `__init__.py`)

---

### Update `__init__.py` (UI & Properties):
- Add:
  ```python
  audio_method: bpy.props.EnumProperty(
      items=[
          ("gemini", "Gemini Direct", "Process audio directly with Gemini"),
          ("whisper", "Whisper", "Transcribe with Whisper first"),
          ("google_stt", "Google Cloud STT", "Transcribe with Google STT first"),
      ],
      name="Audio Method",
      default="whisper"
  )
  ```
- Update:
  ```python
  selected_model: bpy.props.EnumProperty(
      items=[
          ("gemini-2.0-flash", "Gemini 2.0 Flash", "Fast model"),
          ("gemini-2.5-pro-exp-03-25", "Gemini 2.5 Pro", "Most advanced model"),
      ],
      name="Gemini Model",
      default="gemini-2.0-flash"
  )
  ```
- Update `BLENDER_PT_voice_command_panel.draw`:
    - Add dropdown for `audio_method`.
    - Replace single "Start/Stop Voice Command" button with:
        - `BLENDER_OT_connect_client` (connect socket).
        - `BLENDER_OT_disconnect_client` (disconnect socket).
        - `BLENDER_OT_record_command` (record and send audio).

---

### New Operator: `BLENDER_OT_record_command`
- Define:
  ```python
  class BLENDER_OT_record_command(bpy.types.Operator):
      bl_idname = "wm.record_voice_command"
      bl_label = "Record Command"
  ```
- In `execute()`:
    - Check if connected.
    - Call:
      ```python
      blender_voice_client.record_and_send_audio(context, callback=process_voice_client_message)
      ```

---

### Update `blender_voice_client.py`:
- Add imports:
  ```python
  import sounddevice as sd
  import numpy as np
  import base64
  import io
  import wave
  import threading
  ```
- Audio parameters:
  ```python
  SAMPLE_RATE = 16000
  CHANNELS = 1
  DTYPE = 'int16'
  recording_active = threading.Event()
  audio_buffer = io.BytesIO()
  ```

---

### Implement Audio Recording:
- `_audio_recording_thread(callback)`:
    - Uses `sd.InputStream`.
    - Writes to `audio_buffer`.
    - Stops on `recording_active.clear()`.

- `start_audio_recording(callback)`:
    - Resets `audio_buffer`.
    - Starts thread.
    - Calls `callback("Recording started...")`.

- `stop_audio_recording(callback)`:
    - Stops thread.
    - Retrieves audio bytes.
    - Calls `callback("Recording stopped.")`.

- `record_and_send_audio(context, callback)`:
    - Manages full record lifecycle.
    - After recording:
      ```python
      send_audio_command(audio_bytes, model, method, blender_context, callback)
      ```

---

### Implement `send_audio_command`:
- Construct message:
  ```python
  {
    "type": "process_audio",
    "audio_data": base64.b64encode(audio_bytes).decode('utf-8'),
    "model": model,
    "method": method,
    "context": context_dict,
    "audio_format": {"sample_rate": SAMPLE_RATE, "encoding": "wav"}
  }
  ```
- Send:
  ```python
  client_socket.sendall(json.dumps(message).encode())
  ```

---

### Adjust `start_client` / `stop_client`:
- `start_client`:
    - Handles socket connection.
    - Rename `is_listening` ➡️ `is_connected`.
- `stop_client`:
    - Properly disconnect socket.

---

## 🧪 Phase 4: Testing & Refinement
- Manually test:
  - Connection.
  - Recording.
  - Audio sending.
  - Script execution.
- Verify:
  - Error handling: API keys, connection, transcription.
  - UI feedback during recording & processing.
- *(Optional)* Add:
  - Unit tests.
  - Integration tests.

---

✅ **Plan Complete!**  
If you're happy with this, tell me:  
**"Toggle to Act mode"**  
— and I’ll prepare the actual code changes!