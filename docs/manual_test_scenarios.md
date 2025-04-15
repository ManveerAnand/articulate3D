# Manual Test Scenarios for Articulate3D

This document outlines manual test scenarios for System Testing and Acceptance Testing of the Articulate3D Blender addon.

**Tester:** [Name of Tester]
**Date:** [Date of Testing]
**Version Tested:** [Addon Version/Commit ID]

---

## 1. System Testing Scenarios

**Goal:** Verify the end-to-end functionality and error handling of the core voice command pipeline within the Blender environment.

**Prerequisites:**
*   Blender installed.
*   Articulate3D addon installed and enabled.
*   Virtual environment set up (`setup.py` run).
*   Valid Gemini API key configured in the addon UI.
*   Microphone connected and working.
*   Internet connection active.

| Test ID | Scenario Description                     | Steps                                                                                                                               | Expected Result                                                                                                | Actual Result (Pass/Fail) | Notes/Observations |
| :------ | :--------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------- | :------------------------ | :----------------- |
| **Core Functionality** |                                          |                                                                                                                     |                                                                                                                |                           |                    |
| SYS-001 | Create Primitive (Cube)                | 1. Start Blender (default scene). 2. Start Voice Command via UI. 3. Speak "create a cube". 4. Stop Voice Command.                   | A new cube primitive is added to the scene at the origin. Console shows "Listening...", "Processing...", "Executing script...", "Success". |                           |                    |
| SYS-002 | Create Primitive (Sphere)              | 1. Start Blender (default scene). 2. Start Voice Command. 3. Speak "add a uv sphere". 4. Stop Voice Command.                       | A new UV sphere is added to the scene. Console shows appropriate status messages.                              |                           |                    |
| SYS-003 | Select Object                          | 1. Ensure default Cube exists. 2. Deselect all (`Alt+A`). 3. Start Voice Command. 4. Speak "select the cube". 5. Stop Voice Command. | The default Cube becomes the active selected object. Console shows appropriate status messages.                |                           |                    |
| SYS-004 | Transform Object (Move)                | 1. Select the default Cube. 2. Start Voice Command. 3. Speak "move it x 2". 4. Stop Voice Command.                                   | The selected cube moves 2 units along the global X-axis. Console shows appropriate status messages.            |                           |                    |
| SYS-005 | Transform Object (Rotate)              | 1. Select the default Cube. 2. Start Voice Command. 3. Speak "rotate z 45 degrees". 4. Stop Voice Command.                           | The selected cube rotates 45 degrees around the global Z-axis. Console shows appropriate status messages.      |                           |                    |
| SYS-006 | Transform Object (Scale)               | 1. Select the default Cube. 2. Start Voice Command. 3. Speak "scale it up by 1.5". 4. Stop Voice Command.                             | The selected cube scales uniformly by a factor of 1.5. Console shows appropriate status messages.              |                           |                    |
| SYS-007 | Add Modifier (Subdivision)           | 1. Select the default Cube. 2. Start Voice Command. 3. Speak "add subdivision surface modifier". 4. Stop Voice Command.              | A Subdivision Surface modifier is added to the cube. Console shows appropriate status messages.                |                           |                    |
| **UI & Configuration** |                                          |                                                                                                                     |                                                                                                                |                           |                    |
| SYS-008 | Start/Stop Listening                   | 1. Click "Start Voice Command". 2. Observe console. 3. Click "Stop Voice Command". 4. Observe console.                               | Console shows "Listening..." when started and likely stops updating or shows an idle message when stopped. Button states toggle correctly. |                           |                    |
| SYS-009 | Invalid API Key                        | 1. Enter an incorrect API key in the UI. 2. Start Voice Command. 3. Speak "create a cube". 4. Stop Voice Command.                   | Script execution should fail. Console should display an API key related error message from the server.         |                           |                    |
| SYS-010 | Change Gemini Model                    | 1. Select a different valid Gemini model (e.g., "gemini-pro" if available/configured). 2. Start Voice Command. 3. Speak "create a cone". 4. Stop Voice Command. | A cone primitive is added. Console shows processing messages. (Confirms model selection is used).              |                           |                    |
| **Error Handling** |                                          |                                                                                                                     |                                                                                                                |                           |                    |
| SYS-011 | Unintelligible Command                 | 1. Start Voice Command. 2. Mumble or make noise into the microphone. 3. Stop Voice Command.                                        | Console should indicate that speech was not understood or transcription failed (e.g., "Could not understand audio"). |                           |                    |
| SYS-012 | Ambiguous/Invalid Command (for Gemini) | 1. Start Voice Command. 2. Speak "make it awesome" or "do something cool". 3. Stop Voice Command.                                  | Console should display an error message indicating the command could not be processed or generated script failed (e.g., "# Error: Command cannot be processed."). |                           |                    |
| SYS-013 | Network Error (Simulated)              | 1. Disconnect internet after starting server/client. 2. Start Voice Command. 3. Speak "create a cube". 4. Stop Voice Command.       | Console should display an error related to network connectivity or API call failure.                           |                           | (Difficult to test reliably) |
| SYS-014 | Script Execution Error                 | 1. Start Voice Command. 2. Speak a command likely to generate invalid Blender script (e.g., "delete everything important"). 3. Stop. | Console should show "Executing script..." followed by an execution error message and status (e.g., "Error executing script: ..."). Command History should show Error status. |                           |                    |

---

## 2. Acceptance Testing Scenarios

**Goal:** Evaluate the addon's usability, performance, and overall suitability for the user (project team).

**Instructions:** Perform these tests in a realistic Blender workflow. Record observations and subjective feedback.

| Test ID | Scenario Description          | Steps                                                                                                | Expected Outcome / Metric                                                                                                | Actual Result / Feedback | Notes/Observations |
| :------ | :---------------------------- | :--------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------- | :----------------------- | :----------------- |
| ACC-001 | Basic Workflow Usability    | 1. Model a simple object (e.g., a table) using only voice commands (create primitives, move, scale, join). | Subjective: Was the process intuitive? Was the feedback clear? Were there frustrating moments? Task completion possible? |                          |                    |
| ACC-002 | Command Latency (Simple)    | 1. Time multiple instances of simple commands (e.g., "create cube", "select cube", "move x 1"). Record time from end of speech to action completion. | Average time < 3-5 seconds (as per NFR002). Consistent timing.                                                         | Avg Time:                |                    |
| ACC-003 | Command Latency (Complex)   | 1. Time multiple instances of more complex commands (e.g., "add subdivision surface modifier", "bevel the selected edges"). | Average time reasonable (e.g., < 10 seconds). Consistent timing.                                                       | Avg Time:                |                    |
| ACC-004 | Feedback Clarity            | 1. Perform various actions (success, invalid command, unintelligible speech). Observe console output and UI feedback. | Feedback messages are clear, timely, and accurately reflect the system's state or errors encountered.                    |                          |                    |
| ACC-005 | Robustness / Recovery       | 1. Intentionally trigger errors (invalid API key, disconnect network briefly, invalid commands). 2. Attempt to recover and continue working. | System handles errors gracefully without crashing Blender. User can correct issues (e.g., fix API key) and resume. |                          |                    |
| ACC-006 | Command History Usefulness  | 1. Perform several commands. 2. Review the Command History panel. 3. Try re-executing a command. 4. Try favoriting. | History accurately reflects commands and status. Re-execution works. Favoriting works. Panel is easy to understand.    |                          |                    |
| ACC-007 | Overall Satisfaction        | 1. Use the addon for a short modeling session (10-15 mins).                                          | Subjective: Is the addon helpful? Would you use it? What are the biggest pros/cons?                                      |                          |                    |

---
