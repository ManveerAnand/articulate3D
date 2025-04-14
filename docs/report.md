# Project Report: Articulate3D

**Project Title:** Articulate3D (Blender Voice Addon)

**Team:**
*   Roll No. [Your Roll No.] Name: [Your Name]
*   Roll No. [Teammate Roll No.] Name: [Teammate Name]
*   Roll No. [Teammate Roll No.] Name: [Teammate Name]
*   Roll No. [Teammate Roll No.] Name: [Teammate Name]
*   Roll No. [Teammate Roll No.] Name: [Teammate Name]
    *(Please fill in the actual Roll Numbers and Names)*

---

## Objectives as per the initial excel sheet

*(Please summarize the high-level goals from your original project proposal or requirements sheet here. Example: Voice control for Blender, Gemini API integration, local STT option, error handling, command history, etc.)*

---

## Actual Objectives completed in this project

The following objectives were successfully implemented and verified through code analysis and testing:

*   **Core Voice Command Pipeline:**
    *   Enabled users to control Blender via voice commands.
    *   Integrated Google Gemini API for Natural Language Understanding and Blender Python script generation.
    *   Established a robust client-server architecture using sockets for communication between the Blender addon and a standalone Python server process.
    *   Implemented audio capture from the microphone using `speech_recognition` and `pyaudio`.
    *   Integrated multiple Speech-to-Text (STT) options: OpenAI Whisper (local model) and Google Cloud STT.
    *   Implemented wake word detection using Vosk to activate listening.
    *   Enabled execution of generated Python scripts within Blender's context.
*   **User Interface & Configuration:**
    *   Developed a dedicated panel within Blender's 3D View sidebar for addon control.
    *   Allowed secure configuration of the Google Gemini API key via a password field, stored in a `.env` file.
    *   Provided UI options to select the desired Gemini model and audio processing method (Gemini Direct, Whisper, Google STT).
    *   Included Start/Stop buttons to control the voice listening process.
    *   Implemented a console area in the UI for displaying status messages and basic feedback.
*   **Functionality Enhancements:**
    *   Added a Command History feature displaying recent commands, their status (Success, Error), and the generated script.
    *   Implemented re-execution of commands directly from the history.
    *   Added functionality to "star" or favorite commands for easy access (though UI display for starred list needs refinement).
    *   Implemented structured logging to files (`articulate3d_addon.log`, `articulate3d_server.log`) for both client and server components to aid debugging.
    *   Improved error handling for API interactions, script execution, and communication issues, including sending execution errors back to the server for potential retries.
*   **Setup & Installation:**
    *   Provided a `setup.py` script to create virtual environments (`env`/`env_linux`) and install necessary dependencies.

*(Note: Features like a dedicated UI for starred commands were considered but not implemented in this version.)*

---

## Methodology Implemented

*   **Why did you select only this method in your project?**
    *   **Client-Server Socket Architecture:** This architecture was essential due to Blender's restricted Python environment. Libraries required for audio processing (`PyAudio`, `speech_recognition`, `vosk`, `whisper`) and direct AI API interaction (`google-generativeai`) cannot reliably run within Blender's embedded Python. Separating these functions into a standalone Python server process allows for standard dependency management (using `setup.py` and virtual environments) and avoids conflicts. Sockets provide a standard and effective method for Inter-Process Communication (IPC), enabling the Blender addon (client) to send commands and receive results from the external server.
    *   **Google Gemini API:** Chosen for its state-of-the-art capabilities in understanding natural language instructions and generating corresponding code. Its specific ability to translate conversational commands (like "make the sphere blue and metallic") into executable Blender Python (`bpy`) scripts was key to the project's goal. The use of its chat endpoint allows for maintaining context across multiple commands.

*   **How did you use this method in your project?**
    *   **Client-Server:** The Blender addon (`__init__.py`, `blender_voice_client.py`) serves as the client. It provides the UI panel, handles user interactions (button clicks, configuration changes), starts the server process (`standalone_voice_server.py`), connects via sockets, sends configuration data and text commands (using JSON), receives status updates/scripts/errors (as JSON), queues scripts, and executes them within Blender's main thread using `exec()` via a timer callback (`execute_scripts_timer`). The `standalone_voice_server.py` runs independently, listening for socket connections. It manages audio input (Vosk for wake word, `speech_recognition` for command capture), performs STT (Whisper or Google Cloud STT), constructs prompts including Blender context, interacts with the selected Gemini model's chat session (`process_text_with_chat`), handles retries based on client-reported execution errors, and sends JSON-formatted results back to the client.
    *   **Gemini API:** Implemented in `standalone_voice_server.py` using the `google-generativeai` library. The `process_text_with_chat` function takes the transcribed text and Blender context, formats it into a detailed prompt instructing the AI to generate only Blender Python code (for Blender 4.x, preferring `bpy.data`), and sends it to the appropriate Gemini model's chat session. The server manages the chat history for contextual understanding and includes logic to construct specific retry prompts when the client reports script execution errors.

---

## Which SDLC is followed and Why?

*   **Which?** The **Incremental Development Model**.
*   **Why?** This model was suitable because it allowed for the development and delivery of the core voice-to-script execution pipeline as the first functional increment. This provided a testable and demonstrable base early in the project. Subsequent features like command history, multiple STT methods, wake word detection, and improved error handling were added as later increments, building upon the working core. This approach facilitated manageable development cycles, easier testing of individual components/increments, and flexibility in incorporating refinements based on testing feedback.

---

## Which testing methods are used and why?

A multi-level testing strategy was implemented to ensure code quality and functionality:

*   **Unit Testing (White Box):**
    *   **Methods Used:** Automated tests written using the `pytest` framework and `unittest.mock`. These tests focused on isolating and verifying individual functions within the client (`test_client_unit.py`) and server (`test_server_unit.py`) modules. Key functions tested include context formatting, Gemini API interaction (`process_text_with_chat`), transcription functions (`transcribe_with_whisper`, `transcribe_with_google_stt`), connection logic (`connect_to_server`), message handling, and helper utilities. External dependencies (like APIs, sockets, file system, threading) were mocked to ensure functions were tested in isolation.
    *   **Why:** To verify the internal logic of individual components, catch bugs at the lowest level, facilitate refactoring, and ensure maintainability. Mocking allows testing component logic without relying on external services or complex setups. *This level is essential for verifying the complex logic within the isolated Python modules (server, client helpers).*

*   **Integration Testing (Grey Box):**
    *   **Methods Used:** Automated tests using `pytest` (`test_integration_comms.py`) simulating the client-server interaction. These tests focused on the socket communication protocol, verifying that correctly formatted JSON messages (`configure`, `context_response`, `execution_error`, `process_text`) sent by one component were correctly received and processed by the other, using mocked socket objects.
    *   **Why:** To ensure the client and server can communicate effectively according to the defined JSON protocol, validating the primary interface between the two main architectural components. *This is crucial for verifying the client-server socket communication, which is a key architectural interface in this project.*

*   **System Testing (Black Box):**
    *   **Methods Used:** Manual execution within the Blender environment. Tested end-to-end workflows like speaking a command and observing the result in Blender, including object creation, transformation, and modifier application. Also included testing UI interactions and basic error conditions.
    *   **Why:** To validate that the integrated system meets the functional requirements from a user's perspective within the target Blender environment. *This is necessary because the addon's full functionality is realized only within the Blender environment.*

*   **Acceptance Testing (Black Box):**
    *   **Methods Used:** Manual, user-driven testing (by the project team) focusing on usability, performance (latency measurements for simple/complex commands), feedback clarity, and error recovery.
    *   **Why:** To determine if the addon is practical, efficient, and user-friendly for its intended purpose and meets non-functional requirements. *This is important for evaluating the real-world usability and performance of a voice-driven interface.*

*   **Regression Testing:**
    *   **Methods Used:** Re-running the automated `pytest` suite after code changes. Manually re-testing key system scenarios.
    *   **Why:** To ensure that bug fixes or new feature additions haven't inadvertently broken existing functionality. *This is standard practice to prevent introducing new bugs during development and maintenance.*

---

## Testing Results

*   **Automated Tests:** The automated Unit and Integration test suite (`pytest`) consisting of 50 tests **passed** successfully, verifying core component logic and communication protocols.
*   **Manual System & Acceptance Tests:**
    *(Please fill in results after executing scenarios. Include:*
    *   *Summary of manual E2E command tests (e.g., "Tested 12 commands including creation, selection, movement, rotation, scaling, modifiers. 11/12 succeeded. Failure on 'bevel edges' due to complex selection context.")*
    *   *Performance results (e.g., "Simple commands (create cube, move) averaged 3.5 seconds latency. Modifier commands averaged 6 seconds.")*
    *   *Usability feedback (e.g., "UI is clear, history is useful, wake word occasionally misfires in noisy environment.")*
    *   *Error handling observations (e.g., "Invalid API key correctly reported. Script errors shown in console and history.")*)

---

## Key takeaways from your project

*   **Client-Server for Blender Addons:** A client-server architecture is a viable and often necessary approach to integrate complex external libraries (audio processing, AI SDKs) with Blender's restricted Python environment.
*   **API Integration Challenges:** Relying on external APIs (STT, LLMs) introduces dependencies on network stability, API key security, potential costs, and requires careful handling of API errors and rate limits.
*   **Prompt Engineering is Crucial:** The quality and specificity of prompts sent to the Gemini API directly impact the accuracy and safety of the generated Blender scripts. Iterative refinement of the prompt structure was necessary.
*   **Modularity and SDLC:** Using an Incremental Model allowed for manageable development and testing stages, focusing on delivering the core value proposition first before adding enhancements like command history and improved logging.
*   **Importance of Testing Levels:** Combining Unit, Integration, and System/Acceptance testing provides a more robust verification process than relying on a single method. Automated tests are crucial for regression checking.

---

## Any important (and readable) screenshots from your project (not more than 3)

*(Insert Screenshot 1 Here: e.g., Addon UI Panel in Blender showing status and controls)*

**(Caption for Screenshot 1: Articulate3D UI Panel in Blender's Sidebar)**

*(Insert Screenshot 2 Here: e.g., Blender scene showing an object modified by a voice command, perhaps with the console visible)*

**(Caption for Screenshot 2: Result of executing "create a red cube and move it up")**

*(Insert Screenshot 3 Here: e.g., Command History panel showing successful and failed commands)*

**(Caption for Screenshot 3: Command History displaying recent actions and statuses)**

---
