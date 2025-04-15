# Articulate 3D - Blender Voice Command Addon

Articulate 3D is a Blender addon that allows users to create and manipulate 3D models using voice commands, powered by Google's Gemini AI.

## Key Features

- Voice-controlled 3D modeling in Blender
- Real-time voice recognition and processing (using Vosk for wake word and SpeechRecognition/Whisper/Google Cloud STT/Gemini for commands)
- AI-powered natural language understanding via Google Gemini
- Secure API key management using `.env` file
- Runs necessary Python packages in a dedicated virtual environment to avoid conflicts with Blender's built-in Python.

## Architecture Overview

The addon consists of:

1.  **Blender Addon (`__init__.py`)**: Provides the UI panel in Blender, manages state, queues generated scripts, and communicates with the voice client.
2.  **Voice Client (`blender_voice_client.py`)**: Runs within Blender's Python environment. It starts the standalone server, connects to it via sockets, sends context/configuration, and receives messages/scripts from the server, passing them to the main addon code.
3.  **Standalone Voice Server (`src/standalone_voice_server.py`)**: Runs as a separate Python process in its own virtual environment (`env` or `env_linux`). This handles the heavy lifting:
    *   Loading necessary libraries (Vosk, Whisper, Gemini SDK, etc.).
    *   Listening for the wake word using Vosk.
    *   Capturing command audio using SpeechRecognition.
    *   Transcribing audio (Whisper/Google Cloud STT) or processing audio directly (Gemini).
    *   Interacting with the Google Gemini API to generate Python scripts based on commands and Blender context.
    *   Sending generated scripts or status messages back to the Voice Client via sockets.

## Installation

### Prerequisites

*   **Blender 4.0+**: Download and install from [blender.org](https://www.blender.org/download/).
*   **Python 3.8+**: Ensure Python is installed and accessible from your system's command line (check by opening a terminal/command prompt and typing `python --version`). It's recommended to add Python to your system's PATH during installation.
*   **Git**: Needed to clone the repository. Download from [git-scm.com](https://git-scm.com/downloads).
*   **Microphone**: Required for voice input.
*   **Internet Connection**: Required for downloading dependencies and accessing the Google Gemini API.
*   **Google Gemini API Key**: Obtain from [Google AI Studio](https://aistudio.google.com/app/apikey).

### Installation Steps

**Important:** These steps ensure the addon has its necessary Python packages installed correctly *before* you install it into Blender.

1.  **Clone the Repository**:
    Open your terminal or command prompt, navigate to where you want to store the addon source code, and run:
    ```bash
    git clone https://github.com/ManveerAnand/articulate3D.git
    cd articulate3D
    ```

2.  **Run the Setup Script**:
    This step creates a dedicated Python virtual environment (`env` or `env_linux`) *inside* the `articulate3D` folder and installs dependencies there. **Make sure you are still in the `articulate3D` directory in your terminal** and run:
    ```bash
    python setup.py
    ```
    *   Wait for the script to complete. It might take a few minutes. Look for the "Dependencies installed successfully!" message.
    *   Address any errors during this step (see Troubleshooting below, especially for PyAudio).

3.  **Configure API Key**:
    *   After `setup.py` finishes successfully, find the `.env.example` file in the `articulate3D` directory.
    *   Make a copy of this file and rename the copy to `.env`.
    *   Open the `.env` file with a text editor.
    *   Replace `"your_gemini_api_key_here"` with your actual Google Gemini API key. Save the file.
    ```
    # Example .env content:
    GEMINI_API_KEY=AIzaSyB...your...actual...key...here...
    ```

4.  **Create the Addon ZIP File**:
    *   Navigate **one level up** from the `articulate3D` directory in your file explorer or terminal (so you are looking *at* the `articulate3D` folder).
    *   Create a ZIP archive of the **entire `articulate3D` folder**. Make sure the ZIP file includes the `__init__.py`, `setup.py`, `.env`, `src`, `models`, and the newly created `env` (or `env_linux`) folders directly inside it.
    *   Name the ZIP file something like `articulate3D_addon.zip`.

5.  **Install ZIP in Blender**:
    *   Open Blender (version 4.0 or newer).
    *   Go to `Edit` > `Preferences`.
    *   Click the `Add-ons` tab on the left.
    *   Click the `Install...` button at the top right.
    *   Navigate to where you saved `articulate3D_addon.zip` and select it.
    *   Click `Install Add-on`.
    *   Find "Articulate 3D" in the addons list (you can search for it) and check the box next to its name to enable it.

6.  **Configure API Key in Blender**:
    *   Close the Preferences window.
    *   In the 3D Viewport, press `N` to open the sidebar (if it's not already open).
    *   Find the `Voice` tab.
    *   Paste your Google Gemini API key into the "API Key" field within the addon panel. (This ensures the addon UI can validate the key).
    *   Select your desired Gemini Model and Audio Method.

## Usage

1.  Open the Articulate 3D panel in the 3D View sidebar (`N` key > `Voice` tab).
2.  Ensure your API key is entered.
3.  Click "Start Voice Command". The status should change to "Listening...".
4.  Say the wake word (e.g., "Okay Blender"). The status should change to indicate it's listening for a command.
5.  Speak your command clearly (e.g., "Create a red cube", "Add a sphere and move it up").
6.  The addon will process the command, generate a script, and execute it. Check the "Console Output" section in the panel for status messages and errors.
7.  Click "Stop Voice Command" when finished.

## Troubleshooting

*   **`setup.py` Fails / Dependency Errors**:
    *   Ensure you have Python 3.8+ installed and added to your system PATH.
    *   Try running the terminal/command prompt as an administrator (Windows) or using `sudo` (Linux/macOS) for the `python setup.py` command, although this shouldn't usually be necessary.
    *   **PyAudio Installation Issues**: This is common.
        *   **Windows**: You might need "Microsoft C++ Build Tools". Download the "Build Tools for Visual Studio" from the [Visual Studio website](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022), and during installation, select the "C++ build tools" workload. After installation, try running `python setup.py` again. Alternatively, try installing a pre-compiled PyAudio wheel from a trusted source like Christoph Gohlke's [Unofficial Windows Binaries](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) page (download the `.whl` file matching your Python version and system architecture, then install it using `pip install path/to/downloaded_pyaudio_file.whl` *within the addon's virtual environment* - e.g., `.\env\Scripts\python.exe -m pip install path/to/pyaudio.whl`).
        *   **macOS**: Run `brew install portaudio` before running `python setup.py`.
        *   **Linux (Debian/Ubuntu)**: Run `sudo apt-get update && sudo apt-get install portaudio19-dev python3-dev` before running `python setup.py`.
    
    *   **Whisper/ffmpeg Issues**: If using the Whisper transcription method, ensure `ffmpeg` is installed and available in your system's PATH.
    
        *   **Windows**: Download from the [official ffmpeg website](https://ffmpeg.org/download.html) or install using a package manager like Chocolatey (`choco install ffmpeg`).
        *   **macOS**: `brew install ffmpeg`
        *   **Linux**: `sudo apt update && sudo apt install ffmpeg`

*   **Microphone Not Working / No Voice Input**:
    *   Check the `tests/microphone_test.py` script (run it using the virtual environment's Python: e.g., `.\env\Scripts\python.exe tests/microphone_test.py`).
    *   Ensure the correct microphone is selected as the default input in your Operating System sound settings.
    *   Check OS permissions allow applications (like Python/Blender) to access the microphone.
    *   Try increasing microphone volume/gain in system settings.

*   **API Key Errors**:
    *   Double-check the key in the `.env` file and in the Blender addon panel. Ensure no extra spaces or characters.
    *   Verify your internet connection.
    *   Check your Google AI Studio account to ensure the key is active and has API access enabled.

*   **Addon Not Starting / Not Appearing**:
    *   Check Blender's System Console for errors during startup (Window > Toggle System Console).
    *   Ensure you installed the correct `articulate3D_addon.zip` file created in Step 4.
    *   Verify `setup.py` completed without errors *before* creating the ZIP.

*   **Voice Commands Not Recognized / Incorrect Scripts**:
    *   Speak clearly. Background noise can interfere.
    *   Check the "Console Output" in the addon panel and the `articulate3d_addon.log` / `articulate3d_server.log` files for specific errors from the transcription or AI generation steps.
    *   Ensure the server process is running (you might see a second Python process running when the addon is active).
    *   Try simpler commands first.

## Contributing

Contributions are welcome! Please follow these steps:

1.  Fork the repository
2.  Create a feature branch (`git checkout -b feature/AmazingFeature`)
3.  Make your changes
4.  Commit your changes (`git commit -m 'Add some AmazingFeature'`)
5.  Push to the branch (`git push origin feature/AmazingFeature`)
6.  Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE` file for more information.

## Acknowledgments

*   Google Gemini API
*   Blender Foundation
*   OpenAI Whisper
*   Vosk
*   SpeechRecognition library
*   All Contributors
