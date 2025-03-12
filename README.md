# Articulate 3D - Blender Voice Command Addon

Articulate 3D is a Blender addon that allows users to create and manipulate 3D models using voice commands, powered by Google's Gemini AI.

## Key Features

- Voice-controlled 3D modeling in Blender
- Real-time voice recognition and processing
- AI-powered natural language understanding via Google Gemini
- Secure API key management
- Works within Blender's Python environment

## Architecture Overview

The addon is designed with the following components:

1. **UI Component**: Blender panel interface for controlling voice input
2. **Voice Processing**: Captures and transcribes audio input
3. **Natural Language Understanding**: Processes commands using Gemini AI
4. **Script Generation**: Converts natural language to Blender Python code
5. **Execution Engine**: Safely runs generated scripts in Blender

## Installation

### Prerequisites

- Blender 4.0+
- Internet connection (for API access)
- Microphone
- Google Gemini API key

### Installation Steps

1. **Clone the repository**:
   ```
   git clone https://github.com/yourusername/articulate3D.git
   ```

2. **Run the setup script**:
   ```
   cd articulate3D
   python setup.py
   ```
   This creates a virtual environment and installs dependencies.

3. **Configure API keys**:
   - Copy `.env.example` to `.env`
   - Add your Google Gemini API key

4. **Install in Blender**:
   - Open Blender
   - Go to Edit > Preferences > Add-ons
   - Click 'Install' and select the addon directory
   - Enable the 'Articulate 3D' addon

## Handling Blender's Environment Limitations

Blender uses its own Python environment, which presents challenges for addons requiring external packages. Articulate 3D addresses this in several ways:

1. **Bundled Virtual Environment**: The addon creates its own Python virtual environment during setup, separate from Blender's.

2. **Subprocess Communication**: The addon uses subprocess calls to execute code in the bundled environment while maintaining communication with Blender.

3. **Dependency Management**: Required packages (SpeechRecognition, PyAudio, etc.) are installed in the bundled environment, not Blender's Python environment.

4. **Fallback Mechanisms**: If local processing fails, the addon can use online alternatives for speech recognition.

## Real-time Processing

The addon uses threading to ensure real-time voice processing without blocking Blender's UI:

1. Voice input is captured in a background thread
2. Processing happens asynchronously
3. Results are returned to Blender when ready

## LiveKit Integration (Planned)

Future versions will support LiveKit for enhanced real-time audio processing:

- Lower latency voice recognition
- Better handling of network interruptions
- Potential for collaborative voice commands

## Testing the Addon

### Basic Testing

1. **Install the addon** following the installation steps above

2. **Open the Voice panel** in Blender's 3D View sidebar

3. **Enter your API key** in the configuration section

4. **Click "Start Voice Command"** and speak a simple command like:
   - "Create a red cube"
   - "Add a sphere"
   - "Move the selected object up 2 units"

5. **Verify execution** by checking if the command was properly executed in the 3D view

### Advanced Testing

1. **Test environment handling**:
   - Delete the `env` directory and run setup.py again to verify environment recreation
   - Test on different operating systems to ensure cross-platform compatibility

2. **Test error handling**:
   - Try commands with ambiguous instructions
   - Test with poor audio quality or background noise
   - Disconnect from the internet to test offline behavior

3. **Performance testing**:
   - Test with complex scenes to ensure Blender remains responsive
   - Try rapid successive commands to test queue handling

## Troubleshooting

### Common Issues

1. **Microphone not detected**:
   - Ensure your microphone is properly connected
   - Check system permissions for microphone access

2. **API key errors**:
   - Verify your API key is correctly entered
   - Check internet connectivity

3. **Dependencies not installing**:
   - Run setup.py with administrator privileges
   - Check Python version compatibility (Python 3.8+ recommended)

4. **Addon not appearing in Blender**:
   - Ensure you're installing the correct directory
   - Check Blender's console for error messages

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.