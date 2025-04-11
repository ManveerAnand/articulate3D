import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the src directory to the Python path to allow importing standalone_voice_server
# This assumes the tests are run from the project root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Import functions to be tested
from standalone_voice_server import process_with_gemini, transcribe_audio
# Import speech_recognition for error types
import speech_recognition as sr

# --- Tests for process_with_gemini ---

# Use patch decorators to mock the genai module within the standalone_voice_server scope
@patch('standalone_voice_server.genai')
def test_process_with_gemini_generates_script(mock_genai):
    """
    Test that process_with_gemini successfully generates a script
    when the Gemini API call is successful.
    """
    # Arrange: Configure the mock response text
    expected_script = "import bpy\nbpy.ops.mesh.primitive_cube_add()"
    # Set up the mock structure returned by the mocked genai module
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = expected_script
    mock_model_instance.generate_content.return_value = mock_response
    mock_genai.GenerativeModel.return_value = mock_model_instance

    # Act: Call the function under test
    input_text = "create a cube"
    api_key = "dummy_api_key"
    model_name = "gemini-2.0-flash" # Match default
    actual_script = process_with_gemini(input_text, api_key, model_name)

    # Assert: Check that the genai module was configured
    mock_genai.configure.assert_called_once_with(api_key=api_key)

    # Assert: Check that the model was initialized with the correct name
    # Note: We check the call to the *mocked* genai.GenerativeModel
    mock_genai.GenerativeModel.assert_called_once()
    # We could add more specific checks on model args if needed:
    # mock_genai.GenerativeModel.assert_called_once_with(model_name=model_name, ...)

    # Assert: Check that generate_content was called on the *instance*
    mock_model_instance.generate_content.assert_called_once()
    call_args, _ = mock_model_instance.generate_content.call_args
    prompt_arg = call_args[0]
    assert f"Command: {input_text}" in prompt_arg

    # Assert: Check that the function returned the expected script
    assert actual_script == expected_script


@patch('standalone_voice_server.genai')
def test_process_with_gemini_api_error(mock_genai):
    """
    Test that process_with_gemini returns None when the Gemini API call fails.
    """
    # Arrange: Configure the mock generate_content to raise an exception
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.side_effect = Exception("Simulated API Error")
    mock_genai.GenerativeModel.return_value = mock_model_instance

    # Act: Call the function under test
    input_text = "create a sphere"
    api_key = "dummy_api_key"
    model_name = "gemini-2.0-flash" # Match default
    actual_script = process_with_gemini(input_text, api_key, model_name)

    # Assert: Check that the function returned None
    assert actual_script is None

    # Assert: Check that configure and GenerativeModel were still called
    mock_genai.configure.assert_called_once_with(api_key=api_key)
    mock_genai.GenerativeModel.assert_called_once()
    # Assert: Check that generate_content was called (and raised the error)
    mock_model_instance.generate_content.assert_called_once()


# --- Tests for transcribe_audio ---

# Mock recognizer instance for transcribe_audio tests
mock_recognizer = MagicMock()
# Mock audio data
mock_audio = MagicMock()

@patch('standalone_voice_server.os.environ.get')
def test_transcribe_audio_success_no_key(mock_env_get):
    """Test successful transcription using recognize_google without API key."""
    # Arrange
    mock_recognizer.reset_mock() # Reset mock state for this test
    mock_env_get.return_value = None # No SPEECH_API_KEY
    expected_text = "hello world"
    mock_recognizer.recognize_google.return_value = expected_text
    mock_recognizer.recognize_google.side_effect = None # Clear potential side effects
    mock_recognizer.recognize_sphinx.side_effect = Exception("Should not be called") # Ensure fallback isn't used

    # Act
    result = transcribe_audio(mock_recognizer, mock_audio)

    # Assert
    assert result == expected_text
    mock_recognizer.recognize_google.assert_called_once_with(mock_audio)
    mock_env_get.assert_called_once_with("SPEECH_API_KEY", None)
    mock_recognizer.recognize_sphinx.assert_not_called()


@patch('standalone_voice_server.os.environ.get')
def test_transcribe_audio_success_with_key(mock_env_get):
    """Test successful transcription using recognize_google with API key."""
    # Arrange
    mock_recognizer.reset_mock() # Reset mock state for this test
    api_key = "dummy_speech_key"
    mock_env_get.return_value = api_key # Provide SPEECH_API_KEY
    expected_text = "test command"
    mock_recognizer.recognize_google.return_value = expected_text
    mock_recognizer.recognize_google.side_effect = None
    mock_recognizer.recognize_sphinx.side_effect = Exception("Should not be called")

    # Act
    result = transcribe_audio(mock_recognizer, mock_audio)

    # Assert
    assert result == expected_text
    mock_recognizer.recognize_google.assert_called_once_with(mock_audio, key=api_key)
    mock_env_get.assert_called_once_with("SPEECH_API_KEY", None)
    mock_recognizer.recognize_sphinx.assert_not_called()


@patch('standalone_voice_server.os.environ.get')
def test_transcribe_audio_unknown_value_error(mock_env_get):
    """Test handling of UnknownValueError."""
    # Arrange
    mock_recognizer.reset_mock() # Reset mock state for this test
    mock_env_get.return_value = None
    mock_recognizer.recognize_google.side_effect = sr.UnknownValueError("Audio unintelligible")
    mock_recognizer.recognize_sphinx.side_effect = Exception("Should not be called")

    # Act
    result = transcribe_audio(mock_recognizer, mock_audio)

    # Assert
    assert result is None
    mock_recognizer.recognize_google.assert_called_once_with(mock_audio)
    mock_recognizer.recognize_sphinx.assert_not_called()


@patch('standalone_voice_server.os.environ.get')
def test_transcribe_audio_request_error_no_fallback(mock_env_get):
    """Test handling of RequestError when Sphinx fallback also fails."""
    # Arrange
    mock_recognizer.reset_mock() # Reset mock state for this test
    mock_env_get.return_value = None
    mock_recognizer.recognize_google.side_effect = sr.RequestError("API unavailable")
    # Simulate Sphinx failing as well
    mock_recognizer.recognize_sphinx.side_effect = Exception("Sphinx error")

    # Act
    result = transcribe_audio(mock_recognizer, mock_audio)

    # Assert
    assert result is None
    mock_recognizer.recognize_google.assert_called_once_with(mock_audio)
    mock_recognizer.recognize_sphinx.assert_called_once_with(mock_audio)


@patch('standalone_voice_server.os.environ.get')
def test_transcribe_audio_request_error_with_fallback(mock_env_get):
    """Test handling of RequestError with successful Sphinx fallback."""
    # Arrange
    mock_recognizer.reset_mock() # Reset mock state for this test
    mock_env_get.return_value = None
    mock_recognizer.recognize_google.side_effect = sr.RequestError("API unavailable")
    expected_fallback_text = "offline text"
    mock_recognizer.recognize_sphinx.return_value = expected_fallback_text
    mock_recognizer.recognize_sphinx.side_effect = None # Clear potential side effects

    # Act
    result = transcribe_audio(mock_recognizer, mock_audio)

    # Assert
    assert result == expected_fallback_text
    mock_recognizer.recognize_google.assert_called_once_with(mock_audio)
    mock_recognizer.recognize_sphinx.assert_called_once_with(mock_audio)
