import pytest
from unittest.mock import patch, MagicMock
import sys
import os
import socket
import json
import threading # Import threading to potentially mock Event

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the client module functions
import blender_voice_client

# --- Integration Tests for Client Message Handling ---

@patch('blender_voice_client.stop_flag') # Patch the global stop_flag with a MagicMock
def test_client_receives_script_message(mock_stop_flag_mock): # Renamed arg for clarity
    """
    Integration Test: Verify client correctly processes a script message received via socket.
    """
    # Arrange
    mock_socket_instance = MagicMock(spec=socket.socket) # Mock the socket object
    blender_voice_client.client_socket = mock_socket_instance # Assign mock to global client_socket
    mock_callback = MagicMock() # Mock the callback function

    # Prepare the message data
    script_content = "import bpy; bpy.ops.mesh.primitive_cube_add()"
    message_json = {"status": "script", "message": "Received script", "script": script_content}
    message_bytes = json.dumps(message_json).encode('utf-8')

    # Configure the mock socket's recv method:
    # 1. Return the message bytes
    # 2. Raise socket.timeout to simulate waiting after the message
    mock_socket_instance.recv.side_effect = [message_bytes, socket.timeout("Simulated timeout")]

    # Configure the mock's is_set attribute:
    # 1. is_set() returns False for the first loop iteration
    # 2. is_set() returns True after the timeout to stop the loop
    mock_stop_flag_mock.is_set.side_effect = [False, True]

    # Act: Call the function that receives messages
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    # Check that recv was called (at least once)
    mock_socket_instance.recv.assert_called_with(4096)
    # Check that the callback was called with the correct dictionary
    mock_callback.assert_called_once_with(message_json)
    # Check that settimeout was called
    mock_socket_instance.settimeout.assert_called_with(0.5)


@patch('blender_voice_client.stop_flag') # Patch with MagicMock
def test_client_receives_status_message(mock_stop_flag_mock): # Renamed arg
    """
    Integration Test: Verify client correctly processes a status message.
    """
    # Arrange
    mock_socket_instance = MagicMock(spec=socket.socket)
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    status_text = "Listening for command..."
    message_json = {"status": "info", "message": status_text}
    message_bytes = json.dumps(message_json).encode('utf-8')

    mock_socket_instance.recv.side_effect = [message_bytes, socket.timeout("Simulated timeout")]
    # Configure the is_set attribute of the mock
    mock_stop_flag_mock.is_set.side_effect = [False, True]

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_called_with(4096)
    # Callback should receive just the message string for non-script status
    mock_callback.assert_called_once_with(status_text)


@patch('blender_voice_client.stop_flag') # Patch with MagicMock
def test_client_handles_server_disconnect(mock_stop_flag_mock): # Renamed arg
    """
    Integration Test: Verify client handles server disconnect (recv returns empty bytes).
    """
    # Arrange
    mock_socket_instance = MagicMock(spec=socket.socket)
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    # Configure recv to return empty bytes, simulating disconnect
    mock_socket_instance.recv.return_value = b''
    # Stop flag should not be needed as the loop should break on empty recv
    # Configure the is_set attribute of the mock
    mock_stop_flag_mock.is_set.return_value = False

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_called_once_with(4096)
    mock_callback.assert_called_once_with("Connection closed by server")


@patch('blender_voice_client.stop_flag') # Patch with MagicMock
def test_client_handles_json_decode_error(mock_stop_flag_mock): # Renamed arg
    """
    Integration Test: Verify client handles JSONDecodeError gracefully.
    """
    # Arrange
    mock_socket_instance = MagicMock(spec=socket.socket)
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    invalid_json_bytes = b'{"status": "error", "message": "bad json'

    # Configure recv to return invalid bytes, then timeout
    mock_socket_instance.recv.side_effect = [invalid_json_bytes, socket.timeout("Simulated timeout")]
    # Configure the is_set attribute of the mock
    mock_stop_flag_mock.is_set.side_effect = [False, True]

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_called_with(4096)
    # Check that the callback reported a decoding error
    mock_callback.assert_called_once()
    args, _ = mock_callback.call_args
    assert "Error decoding message" in args[0]
