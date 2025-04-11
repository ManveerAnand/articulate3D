import pytest
from unittest.mock import patch, MagicMock, ANY
import pytest
from unittest.mock import patch, MagicMock, ANY
import sys
import os
import socket
import json # <-- Import json

# Add the project root directory to the Python path to allow importing blender_voice_client
# Assumes tests are run from the project root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the module/functions to be tested
import blender_voice_client

# --- Tests for connect_to_server ---

# Use patch to mock the socket module used within blender_voice_client
@patch('blender_voice_client.socket')
def test_connect_to_server_success(mock_socket):
    """Test successful connection to the server."""
    # Arrange
    mock_socket_instance = MagicMock()
    mock_socket.socket.return_value = mock_socket_instance
    mock_callback = MagicMock()

    # Reset global state potentially modified by other tests
    blender_voice_client.client_socket = None

    # Act
    result = blender_voice_client.connect_to_server(callback=mock_callback)

    # Assert
    assert result is True
    # Assert using the mocked socket constants
    mock_socket.socket.assert_called_once_with(mock_socket.AF_INET, mock_socket.SOCK_STREAM)
    mock_socket_instance.connect.assert_called_once_with((blender_voice_client.HOST, blender_voice_client.PORT))
    # Check if the global variable was set (optional, depends on how strict we want to be)
    assert blender_voice_client.client_socket == mock_socket_instance
    # Check callback calls
    mock_callback.assert_called_once_with("Connected to voice recognition server")


@patch('blender_voice_client.socket')
def test_connect_to_server_failure(mock_socket):
    """Test connection failure."""
    # Arrange
    mock_socket_instance = MagicMock()
    mock_socket.socket.return_value = mock_socket_instance
    # Simulate connection error
    connect_error = socket.error("Connection refused")
    mock_socket_instance.connect.side_effect = connect_error
    mock_callback = MagicMock()

    # Reset global state
    blender_voice_client.client_socket = None

    # Act
    result = blender_voice_client.connect_to_server(callback=mock_callback)

    # Assert
    assert result is False
    # Assert using the mocked socket constants
    mock_socket.socket.assert_called_once_with(mock_socket.AF_INET, mock_socket.SOCK_STREAM)
    mock_socket_instance.connect.assert_called_once_with((blender_voice_client.HOST, blender_voice_client.PORT))
    # Check if the global variable holds the created (but unconnected) socket
    assert blender_voice_client.client_socket == mock_socket_instance # Adjusted assertion
    # Check callback calls
    mock_callback.assert_called_once_with(f"Error connecting to server: {connect_error}")


# --- Tests for receive_messages ---

# Note: We no longer need recv_side_effect_factory

@patch('blender_voice_client.json.loads') # Patch only json.loads
@patch('blender_voice_client.stop_flag') # Patch the global stop_flag
def test_receive_messages_script_success(mock_stop_flag, mock_json_loads):
    """Test receiving and processing a valid script message."""
    # Arrange
    mock_socket_instance = MagicMock()
    blender_voice_client.client_socket = mock_socket_instance # Set global socket
    mock_callback = MagicMock()

    script_content = "import bpy; bpy.ops.mesh.primitive_cube_add()"
    # Simulate receiving one message then stopping
    message_json = {"status": "script", "message": "Received script", "script": script_content}
    message_bytes = json.dumps(message_json).encode()

    # Configure stop_flag mock: is_set returns False initially, then True after the timeout
    mock_stop_flag.is_set.side_effect = [False, True]
    # Configure recv mock: return message bytes, then raise timeout
    mock_socket_instance.recv.side_effect = [message_bytes, socket.timeout("Simulated timeout after message")]
    mock_json_loads.return_value = message_json # Ensure json.loads returns the dict

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.settimeout.assert_called_with(0.5)
    mock_socket_instance.recv.assert_called_with(4096)
    mock_json_loads.assert_called_once_with(message_bytes.decode())
    # Callback should receive the dict with the script
    mock_callback.assert_called_once_with(message_json)


@patch('blender_voice_client.json.loads') # Patch only json.loads
@patch('blender_voice_client.stop_flag')
def test_receive_messages_status_success(mock_stop_flag, mock_json_loads):
    """Test receiving and processing a valid status message."""
    # Arrange
    mock_socket_instance = MagicMock()
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    status_message = "Listening..."
    message_json = {"status": "info", "message": status_message}
    message_bytes = json.dumps(message_json).encode()

    mock_stop_flag.is_set.side_effect = [False, True] # Stop after one message
    # Configure recv mock: return message bytes, then raise timeout
    mock_socket_instance.recv.side_effect = [message_bytes, socket.timeout("Simulated timeout after message")]
    mock_json_loads.return_value = message_json

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_called_with(4096)
    mock_json_loads.assert_called_once_with(message_bytes.decode())
    # Callback should receive just the message string for non-script types
    mock_callback.assert_called_once_with(status_message)


@patch('blender_voice_client.json.loads') # Patch only json.loads
@patch('blender_voice_client.stop_flag')
def test_receive_messages_json_decode_error(mock_stop_flag, mock_json_loads):
    """Test handling of JSONDecodeError."""
    # Arrange
    mock_socket_instance = MagicMock()
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    invalid_json_bytes = b'{"status": "info", message": "incomplete json"' # Missing quote

    mock_stop_flag.is_set.side_effect = [False, True] # Stop after one attempt
    # Configure recv mock: return invalid bytes, then raise timeout
    mock_socket_instance.recv.side_effect = [invalid_json_bytes, socket.timeout("Simulated timeout after message")]
    decode_error = json.JSONDecodeError("Expecting property name enclosed in double quotes", "test", 0)
    mock_json_loads.side_effect = decode_error

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_called_with(4096)
    mock_json_loads.assert_called_once_with(invalid_json_bytes.decode())
    mock_callback.assert_called_once_with(f"Error decoding message: {decode_error}")


@patch('blender_voice_client.json.loads') # Patch only json.loads
@patch('blender_voice_client.stop_flag')
def test_receive_messages_server_disconnect(mock_stop_flag, mock_json_loads):
    """Test handling when server disconnects (recv returns empty bytes)."""
    # Arrange
    mock_socket_instance = MagicMock()
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    # Simulate receiving empty bytes
    mock_stop_flag.is_set.return_value = False # Allow loop to run once
    mock_socket_instance.recv.return_value = b'' # Simulate disconnect

    # Act
    blender_voice_client.receive_messages(callback=mock_callback) # Loop should break after receiving b''

    # Assert
    mock_socket_instance.recv.assert_called_with(4096)
    mock_json_loads.assert_not_called() # Should not try to decode empty bytes
    mock_callback.assert_called_once_with("Connection closed by server")


@patch('blender_voice_client.json.loads') # Patch only json.loads
@patch('blender_voice_client.stop_flag')
def test_receive_messages_socket_timeout(mock_stop_flag, mock_json_loads):
    """Test that socket timeout is handled gracefully."""
    # Arrange
    mock_socket_instance = MagicMock()
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    # Simulate timeout, then stop
    mock_stop_flag.is_set.side_effect = [False, True] # Allow loop to run once, then stop
    mock_socket_instance.recv.side_effect = socket.timeout # recv raises timeout

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_called_once_with(4096) # Should be called once before timeout stops it
    mock_json_loads.assert_not_called()
    mock_callback.assert_not_called() # No actual message or error received


@patch('blender_voice_client.json.loads') # Patch only json.loads
@patch('blender_voice_client.stop_flag')
def test_receive_messages_stops_on_flag(mock_stop_flag, mock_json_loads):
    """Test that the loop exits immediately if stop_flag is set."""
    # Arrange
    mock_socket_instance = MagicMock()
    blender_voice_client.client_socket = mock_socket_instance
    mock_callback = MagicMock()

    # Simulate stop flag being set from the beginning
    mock_stop_flag.is_set.return_value = True

    # Act
    blender_voice_client.receive_messages(callback=mock_callback)

    # Assert
    mock_socket_instance.recv.assert_not_called() # Loop should exit before recv
    mock_json_loads.assert_not_called()
    mock_callback.assert_not_called()


# --- Tests for start_client / stop_client ---

@patch('blender_voice_client.threading.Thread')
@patch('blender_voice_client.connect_to_server')
@patch('blender_voice_client.start_voice_server')
@patch('blender_voice_client.stop_client') # Mock stop_client to prevent interference in start test
def test_start_client_success(mock_stop_client, mock_start_server, mock_connect, mock_thread_class):
    """Test successful client startup."""
    # Arrange
    mock_start_server.return_value = MagicMock() # Simulate successful server process start
    mock_connect.return_value = True # Simulate successful connection
    mock_thread_instance = MagicMock()
    mock_thread_class.return_value = mock_thread_instance
    mock_callback = MagicMock()

    # Reset globals
    blender_voice_client.client_thread = None
    blender_voice_client.stop_flag = MagicMock() # Use a mock to check clear/reset

    # Act
    result = blender_voice_client.start_client(callback=mock_callback)

    # Assert
    assert result is True
    mock_start_server.assert_called_once()
    mock_connect.assert_called_once_with(mock_callback)
    # Check that a new Event was created for stop_flag (or clear was called if it existed)
    # Note: The actual code reassigns stop_flag = threading.Event(), difficult to assert directly.
    # We can check if the mock we assigned was replaced, or trust the code review.
    # Let's assert the thread was created and started correctly.
    mock_thread_class.assert_called_once_with(
        target=blender_voice_client.receive_messages,
        args=(mock_callback,),
        daemon=True
    )
    mock_thread_instance.start.assert_called_once()
    assert blender_voice_client.client_thread == mock_thread_instance
    mock_callback.assert_any_call("Voice recognition client started")


@patch('blender_voice_client.threading.Thread')
@patch('blender_voice_client.connect_to_server')
@patch('blender_voice_client.start_voice_server')
@patch('blender_voice_client.stop_client')
def test_start_client_connection_fails(mock_stop_client, mock_start_server, mock_connect, mock_thread_class):
    """Test client startup when connection fails."""
    # Arrange
    mock_start_server.return_value = MagicMock()
    mock_connect.return_value = False # Simulate connection failure
    mock_callback = MagicMock()

    # Reset globals
    blender_voice_client.client_thread = None
    blender_voice_client.stop_flag = MagicMock()

    # Act
    result = blender_voice_client.start_client(callback=mock_callback)

    # Assert
    assert result is False
    mock_start_server.assert_called_once()
    mock_connect.assert_called_once_with(mock_callback)
    mock_thread_class.assert_not_called() # Thread should not start if connection fails
    mock_callback.assert_any_call("Failed to connect to voice recognition server")


# Note: Testing stop_client fully requires managing the state of client_socket and client_thread
@patch('blender_voice_client.stop_flag') # Patch the global Event
def test_stop_client_signals_stop_and_closes_socket(mock_stop_flag_event):
    """Test that stop_client signals the event and closes the socket."""
    # Arrange
    mock_socket_instance = MagicMock()
    mock_thread_instance = MagicMock()
    mock_thread_instance.is_alive.return_value = False # Simulate thread already finished
    mock_callback = MagicMock()

    # Set global state
    blender_voice_client.client_socket = mock_socket_instance
    blender_voice_client.client_thread = mock_thread_instance
    # Assign the patched event to the global variable for the test
    blender_voice_client.stop_flag = mock_stop_flag_event

    # Act
    result = blender_voice_client.stop_client(callback=mock_callback)

    # Assert
    assert result is True
    mock_stop_flag_event.set.assert_called_once()
    mock_socket_instance.close.assert_called_once()
    assert blender_voice_client.client_socket is None # Check socket is reset
    # Join is only called if thread is alive, which it wasn't in this test setup
    mock_thread_instance.join.assert_not_called() # Corrected assertion
    mock_callback.assert_called_once_with("Voice recognition client stopped")


@patch('blender_voice_client.stop_flag')
def test_stop_client_when_already_stopped(mock_stop_flag_event):
    """Test stop_client when socket/thread are already None."""
    # Arrange
    mock_callback = MagicMock()

    # Set global state to stopped
    blender_voice_client.client_socket = None
    blender_voice_client.client_thread = None
    blender_voice_client.stop_flag = mock_stop_flag_event # Assign patched event

    # Act
    result = blender_voice_client.stop_client(callback=mock_callback)

    # Assert
    assert result is True
    mock_stop_flag_event.set.assert_called_once() # Should still signal stop
    mock_callback.assert_called_once_with("Voice recognition client stopped")


# TODO: Add tests for get_python_executable / start_voice_server (might be lower priority)
