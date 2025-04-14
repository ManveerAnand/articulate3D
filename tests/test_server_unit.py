import pytest
from unittest.mock import patch, MagicMock, ANY
import sys
import os
import socket
import json
import io
import wave
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Import functions/classes to be tested from the server module
import standalone_voice_server as server_module
from standalone_voice_server import (
    format_blender_context,
    process_text_with_chat,
    process_audio_with_chat,
    transcribe_with_whisper,
    transcribe_with_google_stt,
    is_socket_connected,
    close_socket
)
# Import actual classes for spec/patching
from socket import socket as actual_socket_class

# --- Tests for format_blender_context ---

def test_format_blender_context_empty():
    assert format_blender_context(None) == "No Blender context provided."
    assert format_blender_context({}) == "No Blender context provided."

def test_format_blender_context_basic():
    context = {"scene_name": "MyScene", "mode": "EDIT"}
    expected = "Scene: MyScene\nMode: EDIT\nActive Object: None\nSelected Objects: []\nOther Scene Objects: []"
    assert format_blender_context(context) == expected

def test_format_blender_context_with_active_object():
    context = {
        "scene_name": "MyScene",
        "mode": "OBJECT",
        "active_object": {
            "name": "Cube",
            "type": "MESH",
            "location": "(1, 2, 3)",
            "rotation_euler": "(0, 0, 0)",
            "scale": "(1, 1, 1)"
        }
    }
    expected = "Scene: MyScene\nMode: OBJECT\nActive Object: Cube (Type: MESH, Loc: (1, 2, 3), Rot: (0, 0, 0), Scale: (1, 1, 1))\nSelected Objects: []\nOther Scene Objects: []"
    assert format_blender_context(context) == expected

def test_format_blender_context_with_selected_objects():
    context = {
        "scene_name": "MyScene",
        "mode": "OBJECT",
        "selected_objects": [
            {"name": "Cube", "type": "MESH"},
            {"name": "Light", "type": "LIGHT"}
        ]
    }
    expected = "Scene: MyScene\nMode: OBJECT\nActive Object: None\nSelected Objects: [Cube (MESH), Light (LIGHT)]\nOther Scene Objects: []"
    assert format_blender_context(context) == expected

def test_format_blender_context_with_scene_objects():
    context = {
        "scene_name": "MyScene",
        "mode": "OBJECT",
        "scene_objects": ["Camera", "Lamp"]
    }
    expected = "Scene: MyScene\nMode: OBJECT\nActive Object: None\nSelected Objects: []\nOther Scene Objects: [Camera, Lamp]"
    assert format_blender_context(context) == expected

def test_format_blender_context_full():
    context = {
        "scene_name": "ComplexScene",
        "mode": "SCULPT",
        "active_object": {"name": "Sphere", "type": "MESH", "location": "(0,0,0)", "rotation_euler":"(0,0,0)", "scale":"(2,2,2)"},
        "selected_objects": [{"name": "Sphere", "type": "MESH"}],
        "scene_objects": ["Cube", "Camera"]
    }
    expected = "Scene: ComplexScene\nMode: SCULPT\nActive Object: Sphere (Type: MESH, Loc: (0,0,0), Rot: (0,0,0), Scale: (2,2,2))\nSelected Objects: [Sphere (MESH)]\nOther Scene Objects: [Cube, Camera]"
    assert format_blender_context(context) == expected

# --- Tests for process_text_with_chat ---

@pytest.fixture
def mock_chat_session():
    """Fixture to create a mock chat session."""
    session = MagicMock()
    # Configure default successful response structure
    response = MagicMock()
    part = MagicMock()
    part.text = "import bpy\nbpy.ops.mesh.primitive_cube_add()"
    response.parts = [part]
    response.text = None
    response.prompt_feedback = None # No blocking by default
    session.send_message.return_value = response
    return session

def test_process_text_with_chat_success(mock_chat_session):
    """Test successful script generation via text."""
    input_text = "make a cube"
    context = {"mode": "OBJECT"}
    expected_script = "import bpy\nbpy.ops.mesh.primitive_cube_add()"

    actual_script = process_text_with_chat(mock_chat_session, input_text, context)

    assert actual_script == expected_script
    mock_chat_session.send_message.assert_called_once()
    call_args, call_kwargs = mock_chat_session.send_message.call_args
    prompt = call_args[0]
    # Check for key components instead of exact match
    assert f"**Command:** {input_text}" in prompt
    assert "**Current Blender Context:**" in prompt
    assert format_blender_context(context) in prompt
    assert "generation_config" in call_kwargs
    assert "safety_settings" in call_kwargs

def test_process_text_with_chat_api_error(mock_chat_session):
    """Test handling of API errors during text processing."""
    mock_chat_session.send_message.side_effect = Exception("Simulated API Error")
    input_text = "make a sphere"
    context = {"mode": "OBJECT"}

    actual_script = process_text_with_chat(mock_chat_session, input_text, context)

    assert actual_script is None
    mock_chat_session.send_message.assert_called_once() # Ensure it was called

def test_process_text_with_chat_blocked(mock_chat_session):
    """Test handling of blocked responses."""
    # Configure response for blocking
    blocked_response = MagicMock()
    feedback = MagicMock()
    feedback.block_reason = "SAFETY"
    blocked_response.parts = []
    blocked_response.text = None
    blocked_response.prompt_feedback = feedback
    mock_chat_session.send_message.return_value = blocked_response

    input_text = "do something harmful"
    context = {"mode": "OBJECT"}

    actual_script = process_text_with_chat(mock_chat_session, input_text, context)

    assert actual_script is None # Should return None on blocked content
    mock_chat_session.send_message.assert_called_once()

def test_process_text_with_chat_no_text_in_response(mock_chat_session):
    """Test handling when response has no text part."""
    # Configure response with no text
    no_text_response = MagicMock()
    no_text_response.parts = [] # Or parts[0] has no .text
    no_text_response.text = None
    no_text_response.prompt_feedback = None
    mock_chat_session.send_message.return_value = no_text_response

    input_text = "a complex command"
    context = {"mode": "OBJECT"}

    actual_script = process_text_with_chat(mock_chat_session, input_text, context)

    assert actual_script is None # Should return None if no valid script text
    mock_chat_session.send_message.assert_called_once()

def test_process_text_with_chat_error_comment_response(mock_chat_session):
    """Test handling when Gemini returns an error comment."""
    # Configure response with error comment
    error_response = MagicMock()
    part = MagicMock()
    part.text = "# Error: Command cannot be processed."
    error_response.parts = [part]
    error_response.text = None
    error_response.prompt_feedback = None
    mock_chat_session.send_message.return_value = error_response

    input_text = "invalid command"
    context = {"mode": "OBJECT"}

    actual_script = process_text_with_chat(mock_chat_session, input_text, context)

    assert actual_script is None # Should return None if script contains # Error:
    mock_chat_session.send_message.assert_called_once()

def test_process_text_with_chat_no_session_provided():
    """Test behavior when no chat session is passed."""
    input_text = "make a light"
    context = {"mode": "OBJECT"}

    actual_script = process_text_with_chat(None, input_text, context)

    assert actual_script is None

# --- Tests for transcribe_with_whisper ---

@patch('standalone_voice_server.os.path.exists') # Patch os.path.exists as well
@patch('standalone_voice_server.whisper.load_model')
@patch('standalone_voice_server.tempfile.NamedTemporaryFile')
@patch('standalone_voice_server.os.remove')
def test_transcribe_with_whisper_success(mock_os_remove, mock_tempfile, mock_load_model, mock_os_path_exists):
    """Test successful transcription with Whisper."""
    # Arrange Mocks
    mock_os_path_exists.return_value = True # Ensure exists returns True for the finally block check
    mock_model_instance = MagicMock()
    mock_model_instance.transcribe.return_value = {"text": "hello whisper"}
    mock_load_model.return_value = mock_model_instance

    mock_file_handle = MagicMock()
    # Ensure __exit__ is mocked correctly for the 'with' statement
    mock_file_handle = MagicMock()
    mock_file_handle.name = "dummy/path/temp_audio.wav" # Keep a consistent dummy path
    mock_file_handle.__enter__.return_value = mock_file_handle
    mock_file_handle.__exit__.return_value = None # Simulate normal exit
    mock_tempfile.return_value = mock_file_handle

    audio_bytes = b"fake_wav_data"
    # Reset mocks that might persist state
    server_module.whisper_model_cache.clear()
    mock_load_model.reset_mock()
    mock_model_instance.reset_mock()
    mock_os_remove.reset_mock()
    mock_tempfile.reset_mock()

    # Act
    result = transcribe_with_whisper(audio_bytes)

    # Assert
    assert result == "hello whisper"
    mock_load_model.assert_called_once_with("small")
    # Check that the directory path calculation is attempted (using ANY for Path object)
    mock_tempfile.assert_called_once_with(dir=ANY, suffix=".wav", delete=False)
    mock_file_handle.write.assert_called_once_with(audio_bytes)
    mock_model_instance.transcribe.assert_called_once_with(mock_file_handle.name, fp16=False)
    mock_os_remove.assert_called_once_with(mock_file_handle.name)

@patch('standalone_voice_server.whisper.load_model')
def test_transcribe_with_whisper_model_load_error(mock_load_model):
    """Test Whisper transcription failure due to model loading error."""
    # Reset mocks
    server_module.whisper_model_cache.clear()
    mock_load_model.reset_mock()
    mock_load_model.side_effect = Exception("Model load failed")
    audio_bytes = b"fake_wav_data"

    result = transcribe_with_whisper(audio_bytes)

    assert result is None
    mock_load_model.assert_called_once_with("small")

@patch('standalone_voice_server.os.path.exists') # Patch os.path.exists
@patch('standalone_voice_server.whisper.load_model')
@patch('standalone_voice_server.tempfile.NamedTemporaryFile')
@patch('standalone_voice_server.os.remove')
def test_transcribe_with_whisper_transcription_error(mock_os_remove, mock_tempfile, mock_load_model, mock_os_path_exists):
    """Test Whisper transcription failure during the transcribe call."""
    # Arrange Mocks & Reset
    mock_os_path_exists.return_value = True # Ensure exists returns True for the finally block check
    server_module.whisper_model_cache.clear()
    mock_load_model.reset_mock()
    mock_os_remove.reset_mock()
    mock_tempfile.reset_mock()

    mock_model_instance = MagicMock()
    mock_model_instance.transcribe.side_effect = Exception("Transcription failed")
    mock_load_model.return_value = mock_model_instance # Simulate successful load

    mock_file_handle = MagicMock()
    mock_file_handle.name = "dummy/path/temp_audio.wav"
    mock_file_handle.__enter__.return_value = mock_file_handle
    mock_file_handle.__exit__.return_value = None
    mock_tempfile.return_value = mock_file_handle

    audio_bytes = b"fake_wav_data"

    # Act
    result = transcribe_with_whisper(audio_bytes)

    # Assert
    assert result is None
    mock_load_model.assert_called_once_with("small")
    mock_tempfile.assert_called_once()
    mock_model_instance.transcribe.assert_called_once()
    mock_os_remove.assert_called_once_with(mock_file_handle.name) # Should still try to remove temp file

# --- Tests for transcribe_with_google_stt ---

@patch('standalone_voice_server.speech.SpeechClient')
@patch('standalone_voice_server.os.getenv')
def test_transcribe_with_google_stt_success(mock_getenv, mock_speech_client_class):
    """Test successful transcription with Google Cloud STT."""
    # Arrange Mocks
    mock_getenv.return_value = None # Simulate no explicit credentials path
    mock_client_instance = MagicMock()
    mock_response = MagicMock()
    mock_alternative = MagicMock()
    mock_alternative.transcript = "hello google " # Note trailing space for strip() test
    mock_result = MagicMock()
    mock_result.alternatives = [mock_alternative]
    mock_response.results = [mock_result]
    mock_client_instance.recognize.return_value = mock_response
    mock_speech_client_class.return_value = mock_client_instance

    audio_bytes = b"fake_wav_data_google"
    sample_rate = 16000

    # Act
    result = transcribe_with_google_stt(audio_bytes, sample_rate)

    # Assert
    assert result == "hello google" # Check stripping
    mock_getenv.assert_called_once_with("GOOGLE_APPLICATION_CREDENTIALS")
    mock_speech_client_class.assert_called_once_with() # Called with no args for default auth
    mock_client_instance.recognize.assert_called_once()
    call_args, call_kwargs = mock_client_instance.recognize.call_args
    config_arg = call_kwargs.get('config') or call_args[0] # Check config object
    audio_arg = call_kwargs.get('audio') or call_args[1] # Check audio object
    assert config_arg.sample_rate_hertz == sample_rate
    assert config_arg.language_code == "en-US"
    assert audio_arg.content == audio_bytes

@patch('standalone_voice_server.speech.SpeechClient')
@patch('standalone_voice_server.os.getenv')
@patch('standalone_voice_server.Path')
def test_transcribe_with_google_stt_success_with_creds(mock_path, mock_getenv, mock_speech_client_class):
    """Test successful transcription with Google Cloud STT using credentials file."""
    # Arrange Mocks
    cred_path = "/fake/path/creds.json"
    mock_getenv.return_value = cred_path
    mock_path_instance = MagicMock()
    mock_path_instance.is_file.return_value = True
    mock_path.return_value = mock_path_instance

    mock_client_instance = MagicMock()
    mock_response = MagicMock()
    mock_alternative = MagicMock()
    mock_alternative.transcript = "hello google creds"
    mock_result = MagicMock()
    mock_result.alternatives = [mock_alternative]
    mock_response.results = [mock_result]
    mock_client_instance.recognize.return_value = mock_response
    # Mock the class method specifically
    mock_speech_client_class.from_service_account_file.return_value = mock_client_instance

    audio_bytes = b"fake_wav_data_google_creds"
    sample_rate = 48000

    # Act
    result = transcribe_with_google_stt(audio_bytes, sample_rate)

    # Assert
    assert result == "hello google creds"
    mock_getenv.assert_called_once_with("GOOGLE_APPLICATION_CREDENTIALS")
    mock_path.assert_called_once_with(cred_path)
    mock_path_instance.is_file.assert_called_once()
    mock_speech_client_class.from_service_account_file.assert_called_once_with(cred_path)
    mock_client_instance.recognize.assert_called_once()
    call_args, call_kwargs = mock_client_instance.recognize.call_args
    config_arg = call_kwargs.get('config') or call_args[0]
    assert config_arg.sample_rate_hertz == sample_rate

@patch('standalone_voice_server.speech.SpeechClient')
@patch('standalone_voice_server.os.getenv')
def test_transcribe_with_google_stt_api_error(mock_getenv, mock_speech_client_class):
    """Test Google STT failure due to API error."""
    mock_getenv.return_value = None
    mock_client_instance = MagicMock()
    mock_client_instance.recognize.side_effect = Exception("API Error")
    mock_speech_client_class.return_value = mock_client_instance

    audio_bytes = b"fake_wav_data_google_err"
    sample_rate = 16000

    # Act
    result = transcribe_with_google_stt(audio_bytes, sample_rate)

    # Assert
    assert result is None
    mock_client_instance.recognize.assert_called_once()

@patch('standalone_voice_server.speech.SpeechClient')
@patch('standalone_voice_server.os.getenv')
def test_transcribe_with_google_stt_no_results(mock_getenv, mock_speech_client_class):
    """Test Google STT when API returns no results."""
    mock_getenv.return_value = None
    mock_client_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.results = [] # Empty results
    mock_client_instance.recognize.return_value = mock_response
    mock_speech_client_class.return_value = mock_client_instance

    audio_bytes = b"fake_wav_data_google_empty"
    sample_rate = 16000

    # Act
    result = transcribe_with_google_stt(audio_bytes, sample_rate)

    # Assert
    assert result is None
    mock_client_instance.recognize.assert_called_once()

# --- Tests for is_socket_connected ---

def test_is_socket_connected_true():
    # Use actual class for spec
    mock_sock = MagicMock(spec=actual_socket_class)
    mock_sock.fileno.return_value = 1 # Simulate valid file descriptor
    mock_sock.send.return_value = 0 # Simulate successful send of 0 bytes

    assert is_socket_connected(mock_sock) is True
    mock_sock.settimeout.assert_any_call(0.01)
    mock_sock.send.assert_called_once_with(b'')
    mock_sock.settimeout.assert_any_call(None)

def test_is_socket_connected_false_on_error():
    # Use actual class for spec
    mock_sock = MagicMock(spec=actual_socket_class)
    mock_sock.fileno.return_value = 1
    mock_sock.send.side_effect = socket.error("Connection closed")

    assert is_socket_connected(mock_sock) is False
    mock_sock.settimeout.assert_any_call(0.01)
    mock_sock.send.assert_called_once_with(b'')
    mock_sock.settimeout.assert_any_call(None)

def test_is_socket_connected_false_on_none():
    assert is_socket_connected(None) is False

def test_is_socket_connected_false_on_closed_fileno():
    # Use actual class for spec
    mock_sock = MagicMock(spec=actual_socket_class)
    mock_sock.fileno.return_value = -1 # Simulate closed socket
    assert is_socket_connected(mock_sock) is False
    mock_sock.send.assert_not_called() # Should exit early

# --- Tests for close_socket ---

def test_close_socket_success():
    # Use actual class for spec
    mock_sock = MagicMock(spec=actual_socket_class)
    mock_sock.fileno.return_value = 1
    addr = ("127.0.0.1", 12345)

    close_socket(mock_sock, addr)

    mock_sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    mock_sock.close.assert_called_once()

def test_close_socket_already_closed():
    # Use actual class for spec
    mock_sock = MagicMock(spec=actual_socket_class)
    mock_sock.fileno.return_value = 1
    # Simulate error that means already closed (e.g., OSError with errno 107 ENOTCONN)
    mock_sock.shutdown.side_effect = OSError(107, "Socket not connected")
    addr = ("127.0.0.1", 12345)

    close_socket(mock_sock, addr)

    mock_sock.shutdown.assert_called_once_with(socket.SHUT_RDWR) # Attempt shutdown
    mock_sock.close.assert_called_once() # Still attempt close

def test_close_socket_none():
    addr = ("127.0.0.1", 12345)
    # Should not raise error
    close_socket(None, addr)

# TODO: Add tests for process_audio_with_chat (similar structure to text)
# TODO: Add tests for process_captured_command (more complex mocking needed)
