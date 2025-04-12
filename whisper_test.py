import os
import whisper
import sounddevice as sd
import wave # Use standard wave module
import numpy as np
import logging
import sys

# --- Basic Logging Setup ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=log_format, handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)
logger.info("--- Whisper Test Script Started ---")

# --- Configuration ---
DURATION = 5  # seconds
SAMPLE_RATE = 16000 # Hz (Whisper prefers 16kHz)
CHANNELS = 1 # Mono
FILENAME = "test_audio.wav" # Save in the current directory
MODEL_NAME = "small" # Use the base model for faster testing

def run_whisper_test():
    """Records audio, saves it, transcribes it with Whisper, and prints the result."""
    try:
        # --- Record Audio ---
        logger.info(f"Recording {DURATION} seconds of audio...")
        recording = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16')
        sd.wait()  # Wait until recording is finished
        logger.info("Recording finished.")

        # --- Save Audio using wave module ---
        logger.info(f"Saving audio to {FILENAME}...")
        with wave.open(FILENAME, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            # sounddevice uses int16, which is 2 bytes
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(recording.tobytes())
        logger.info(f"Audio saved successfully to {os.path.abspath(FILENAME)}")

        # --- Load Whisper Model ---
        logger.info(f"Loading Whisper model: {MODEL_NAME}...")
        model = whisper.load_model(MODEL_NAME)
        logger.info("Whisper model loaded.")

        # --- Transcribe Audio ---
        logger.info(f"Transcribing {FILENAME}...")
        # Ensure ffmpeg is in PATH or specify its location if needed
        result = model.transcribe(FILENAME)
        transcription = result.get("text", "").strip()
        logger.info(f"Transcription Result: '{transcription}'")

    except Exception as e:
        logger.error(f"An error occurred during the test: {e}", exc_info=True)
        if "ffmpeg" in str(e).lower():
            logger.error("This might be an ffmpeg issue. Ensure ffmpeg is installed and accessible in your system's PATH.")
        if "Permission denied" in str(e):
             logger.error("Permission denied error encountered. Check write permissions for the current directory and read permissions for ffmpeg/temp files.")

    finally:
        # --- Clean up ---
        if os.path.exists(FILENAME):
            try:
                os.remove(FILENAME)
                logger.info(f"Deleted temporary file: {FILENAME}")
            except OSError as e_del:
                logger.error(f"Error deleting temporary file {FILENAME}: {e_del}")
        logger.info("--- Whisper Test Script Finished ---")

if __name__ == "__main__":
    run_whisper_test()
