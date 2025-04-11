**Project Requirements Document: Articulate 3D (Blender Voice Addon)**

**Version:** 1.5 (Post-Initial Development Phase)
**Date:** 11th April 2025

**1. Introduction**

This document outlines the functional, non-functional, and testing requirements for the Articulate 3D Blender Addon. The project aims to enable users to control Blender using voice commands, leveraging Google's Gemini API for natural language understanding and script generation. This version reflects the features implemented in the initial development phase and outlines remaining work and testing requirements for project completion and evaluation. The project follows an **Incremental Development Model**.

**2. Functional Requirements (FR)**

The following table outlines the detailed functional requirements:

| Requirement ID | Description                     | User Story                                                                                                 | Expected Behavior/Outcome                                                                                                                               | Status          | Notes                                                                                                   |
| :------------- | :------------------------------ | :--------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------ | :-------------- | :------------------------------------------------------------------------------------------------------ |
| **Core Voice -> Script Pipeline** |                                 |                                                                                                            |                                                                                                                                                         |                 | **This is the primary implemented increment.**                                                          |
| FR001          | Addon Installation & Setup      | As a developer, I want a setup script that creates a virtual environment and installs necessary dependencies. | Running `setup.py` should create a functional Python environment (`env`/`env_linux`) and install libraries like `SpeechRecognition`, `google-generativeai`, `python-dotenv`, `PyAudio`. | **Done**        | Code: `setup.py`. Handles dependencies and environment setup.                                           |
| FR002          | Blender UI Panel                | As a user, I want a dedicated panel within Blender's UI to manage voice commands.                            | The system should display a panel in the Blender 3D View sidebar ("Voice" category) with controls and feedback areas.                               | **Done**        | Code: `__init__.py` (BLENDER_PT_voice_command_panel).                                                  |
| FR003          | API Key Configuration           | As a user, I want to securely configure my Google Gemini API key within the addon.                           | The UI panel should provide a password field to input the Gemini API key. The key should be stored persistently (e.g., in `.env` file). API key validation should occur. | **Done**        | Code: `__init__.py` (VoiceCommandProperties, update_env_file, validate_api_key), `.env` file.            |
| FR004          | Gemini Model Selection          | As a user, I want to select the specific Gemini model (e.g., Flash, Pro) for processing my commands.         | The UI panel should provide a dropdown menu to select from available Gemini models. The selection should be used for API calls.                     | **Done**        | Code: `__init__.py` (VoiceCommandProperties).                                                          |
| FR005          | Start/Stop Voice Input        | As a user, I want to be able to start and stop the voice command listening process via UI buttons.             | The UI panel should have "Start Voice Command" and "Stop Voice Command" buttons that toggle the listening state (`is_listening`).                       | **Done**        | Code: `__init__.py` (BLENDER_OT_voice_command, BLENDER_OT_stop_voice_command).                         |
| FR006          | Microphone Input Capture        | As a system component, I need to capture audio input from the user's default microphone.                     | The `standalone_voice_server.py` should use `speech_recognition` (and PyAudio) to access the microphone and capture audio segments when listening. | **Done**        | Code: `standalone_voice_server.py` (uses `sr.Microphone()`, `recognizer.listen()`).                     |
| FR007          | Cloud Speech-to-Text (STT)    | As a system component, I need to convert captured voice audio into text using a cloud service.               | The `standalone_voice_server.py` should send captured audio to Google's Speech Recognition service (free tier or API key) and receive text transcription. | **Done**        | Code: `standalone_voice_server.py` (uses `recognizer.recognize_google()`).                            |
| FR008          | Gemini Script Generation        | As a system component, I need to convert the transcribed text into a Blender Python script using Gemini API. | The `standalone_voice_server.py` should send the transcribed text in a prompt to the selected Gemini model API and receive executable Python code.  | **Done**        | Code: `standalone_voice_server.py` (uses `google-generativeai`, `process_with_gemini()`).             |
| FR009          | Client-Server Communication   | As system components, the Blender addon (client) and the voice server need to communicate reliably.            | The `blender_voice_client.py` should connect to the `standalone_voice_server.py` via a local socket. Messages (status, errors, scripts) should be sent as JSON. | **Done**        | Code: `blender_voice_client.py`, `standalone_voice_server.py` (use `socket` module).                    |
| FR010          | Script Execution in Blender     | As the Blender addon, I need to execute the received Python script safely within Blender's context.          | The `__init__.py` script should receive scripts via the socket client, queue them, and execute them using `exec()` within a Blender timer callback. | **Done**        | Code: `__init__.py` (uses `exec()`, `execute_scripts_timer`, `script_queue`).                         |
| FR011          | Basic Console Feedback        | As a user, I want to see status messages and basic feedback about the voice command process in the UI.       | The UI panel's "Console Output" area should display messages like "Listening...", "Processing...", "Executing script...", and basic errors.         | **Done**        | Code: `__init__.py` (updates `console_output` property), messages sent from server/client.           |
| **Planned Features / Next Increments** |                                 |                                                                                                            |                                                                                                                                                         |                 | **Features mentioned in initial docs but not fully implemented.**                                     |
| FR012          | Local STT Processing Option   | As a user concerned about privacy or offline use, I want the option to use local STT instead of the cloud.   | The system should allow configuring and using an offline STT engine (e.g., Vosk, CMU Sphinx) as an alternative to `recognize_google()`.             | **Planned**     | Currently only cloud STT. Sphinx mentioned as *error fallback*, not a primary option. Requires significant work. |
| FR013          | Advanced Error Handling & Logging | As a developer/user, I want robust error handling and detailed logging for easier debugging.                 | The system should implement structured logging (file/console), handle specific errors (API errors, script errors, audio errors), and provide clearer user feedback on failures. | **Planned**     | Current error handling is basic print/console messages. Requires implementing Python's `logging` module.    |
| FR014          | View Command History          | As a user, I want to see a history of my voice commands and the generated scripts.                         | The UI panel should display a list or log of recent commands, their transcription, and the resulting script/status.                                 | **Planned**     | Not implemented in current code.                                                                        |
| FR015          | LiveKit Integration           | As a developer, I want to explore LiveKit for potentially lower latency audio processing.                    | Integrate `livekit-server-sdk` for real-time audio streaming and processing as an alternative backend.                                            | **Planned**     | Dependency can be installed via `setup.py`, but no integration code exists. Low priority for completion. |

**3. Non-Functional Requirements (NFR)**

| Requirement ID | Description        | Details & Measurement                                                                                                                            | Status                 | Notes                                                                                                                                |
| :------------- | :----------------- | :----------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------- | :----------------------------------------------------------------------------------------------------------------------------------- |
| NFR001         | Usability          | The UI should be intuitive. Feedback should be clear and timely. (Measure: User feedback, task completion time).                                  | **Partial**            | Basic UI and feedback exist. Can be improved with better error messages (FR013) and history (FR014).                                    |
| NFR002         | Performance        | Voice command processing (voice -> script execution) should have minimal latency. (Measure: End-to-end time for common commands < 3-5 seconds).     | **Needs Testing**      | Highly dependent on network latency to Google STT/Gemini API. Needs measurement.                                                      |
| NFR003         | Reliability        | The addon and voice server should operate without frequent crashes. Socket connection should be stable. Script execution errors should be handled. | **Needs Testing**      | Client-server architecture seems robust. Needs testing under load and various network conditions. Script execution errors need FR013. |
| NFR004         | Security           | API keys should be handled securely. Generated scripts should not pose a security risk (within Blender's sandbox).                                 | **Partial**            | API key stored in `.env`, UI uses password field. `exec()` is used, relies on Blender's security context. Considered acceptable for addon. |
| NFR005         | Privacy            | User voice data handling should respect privacy.                                                                                                   | **Partial**            | Currently sends voice data to Google STT and text to Gemini. Requires cloud services. Local processing (FR012) needed for full privacy. |
| NFR006         | Scalability        | The architecture should handle increasingly complex commands and potentially more users (if applicable).                                             | **Partial**            | Client-server helps. Scalability mainly limited by Gemini's ability to generate complex scripts and Blender's performance.          |
| NFR007         | Maintainability    | Code should be well-structured, commented, and follow conventions for ease of future development and debugging.                                    | **Needs Review/Improvement** | Code structure exists. Requires review for clarity, comments, and adherence to Python best practices.                                  |

**4. Testing Requirements (TR)**

| Requirement ID | Description                   | Testing Method                             | Expected Outcome                                                                            | Status          | Notes                                                                                                                            |
| :------------- | :---------------------------- | :----------------------------------------- | :------------------------------------------------------------------------------------------ | :-------------- | :------------------------------------------------------------------------------------------------------------------------------- |
| TR001          | Microphone Functionality Test | Manual Execution (`microphone_test.py`)    | Script should detect microphones, capture audio, and ideally perform a basic transcription. | **Done (Basic)** | `microphone_test.py` exists. Useful for initial setup diagnosis.                                                               |
| TR002          | Unit Tests                    | Automated (Pytest)                       | Test critical functions in isolation (e.g., `process_with_gemini`, API key validation).       | **Planned**     | `pytest` is in dependencies, but tests need to be written for key functions in `standalone_voice_server.py` and `__init__.py`.     |
| TR003          | Integration Tests             | Automated/Manual (Pytest/Manual Execution) | Verify communication between `blender_voice_client` and `standalone_voice_server`. Test message formats (JSON). | **Planned**     | Can write pytest scripts that simulate client/server interaction or test manually by running both components.                   |
| TR004          | End-to-End (E2E) Tests        | Manual Execution                           | User speaks command -> Blender performs action correctly. Test various commands (create, move, modify). | **Planned (Manual)** | Essential for demo. Define a set of test commands and expected Blender outcomes. Record success/failure.                         |
| TR005          | Usability Testing             | Manual Execution (User Feedback)           | Gather feedback from team members or peers on ease of use, clarity of UI and feedback.       | **Planned**     | Important for demonstrating user value.                                                                                          |
| TR006          | Performance Testing           | Manual Execution (Timing)                  | Measure time from voice command end to Blender action completion for sample commands.         | **Planned**     | Provides data for NFR002.                                                                                                        |
| TR007          | Error Handling Testing        | Manual Execution                           | Test scenarios like invalid API key, no internet, microphone issues, invalid voice commands.  | **Planned**     | Verify that errors are handled gracefully and reported to the user (relies on FR013 improvements).                              |

---

**How to Use This Document for Your Final Report:**

1.  **Objectives (Initial vs. Actual):**
    *   **Initial:** Summarize the high-level goals from your original proposal/SRS (e.g., voice control, Gemini integration, local processing, error handling, history).
    *   **Actual Completed:** List the Requirements from the PRD marked as **Done** or **Partial**. Focus heavily on the core FR001-FR011 pipeline. Acknowledge "Partial" status where applicable (e.g., NFR001 Usability, NFR005 Privacy).

2.  **Methodology Implemented:**
    *   **Why this method?**
        *   **Client-Server Socket Architecture:** Chosen to overcome Blender's isolated Python environment limitations. Running voice processing/AI in a separate, standard Python process (server) with its own dependencies (managed by `setup.py`) allows using libraries like `SpeechRecognition`, `PyAudio`, and `google-generativeai` which are difficult/impossible to use directly within Blender's Python. Sockets provide a standard, reliable way for the Blender addon (client) to communicate with this external process.
        *   **Google Gemini API:** Selected for its powerful natural language understanding and code generation capabilities, specifically tailored for converting conversational commands into structured Blender Python scripts.
    *   **How did you use this method?**
        *   **Client-Server:** The Blender addon (`__init__.py`, `blender_voice_client.py`) acts as the client. It handles the UI, starts/stops the process, sends control signals, receives status/scripts via a socket connection, and executes scripts using `exec()`. The `standalone_voice_server.py` runs as the server in a separate process (launched by the client). It listens on a socket, captures audio, calls Google STT, calls Gemini API with the text, and sends results (status, scripts, errors) back to the client over the socket.
        *   **Gemini API:** Used within the `standalone_voice_server.py`. A specific prompt instructs Gemini to act as a Blender Python script generator, taking the transcribed user command as input and outputting *only* the executable Python code (FR008).

3.  **SDLC Followed:**
    *   **Which?** Incremental Model.
    *   **Why?** Allowed delivery of core, usable functionality (voice -> script -> execution pipeline) early (Increment 1: FR001-FR011). This provides a working base for demonstration and further development. It makes testing easier as each increment can be tested individually. It fits well with developing complex features like Local Processing (FR012) or Advanced Error Handling (FR013) in subsequent increments.

4.  **Testing Methods Used:**
    *   Mention the testing types from the TR section.
    *   **Actual Done:** Manual diagnosis (`microphone_test.py` - TR001). Manual E2E testing during development (implicitly TR004).
    *   **Why these methods?** `microphone_test.py` was essential for basic hardware setup validation. Manual E2E testing was necessary to verify the core workflow during development. *Crucially, state that you plan to add Unit (TR002) and Integration (TR003) tests for improved reliability and maintainability, even if basic.*
    *   **Suggestion:** Try to add *at least one or two simple unit tests* using `pytest` (e.g., test the `process_with_gemini` function with mock input/output) so you can concretely say you *used* unit testing.

5.  **Testing Results:**
    *   Report the outcome of `microphone_test.py`.
    *   Report the results of your manual E2E testing (TR004). List 5-10 specific commands you tested (e.g., "create a cube", "move selected object x 2", "add subdivision surface modifier") and whether they succeeded or failed. Be honest about failures – it shows thorough testing.
    *   If you add unit tests, report their pass/fail status.
    *   Report results of performance testing (TR006) if you measure it (e.g., "Simple commands took approx X seconds").

6.  **Key Takeaways:**
    *   Overcoming Blender's Python environment limitations requires architectural solutions (like the client-server model).
    *   Cloud APIs (STT, Gemini) offer powerful capabilities but introduce dependencies (network, API keys) and potential privacy concerns.
    *   Clear prompting is crucial for effective AI code generation (Gemini).
    *   Incremental development allowed focusing on delivering the core value proposition first.
    *   Robust error handling and comprehensive testing are essential next steps for production readiness.

7.  **Screenshots:**
    *   The Blender UI Panel (FR002).
    *   Blender showing an object created/modified by a voice command.
    *   Maybe a snippet of the console output showing the process (FR011).

**Final Advice:**

*   **Focus on the Core:** Your main achievement is the voice -> STT -> Gemini -> Script -> Execution pipeline (FR001-FR011). Emphasize this in your report and demo.
*   **Manage Scope:** Don't over-promise on the "Planned" items. Frame them as future work or the next increments. Your grade depends on achieving what you claim you *completed*.
*   **Testing is Key:** The instructor mentioned testing. Bolster this section. Run the manual E2E tests systematically and report results. Add a few simple unit tests if possible.
*   **Honesty:** Acknowledge limitations (e.g., cloud dependency, basic error handling) and frame them as areas for future improvement identified through the development process. This shows critical thinking.
