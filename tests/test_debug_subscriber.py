import sys
import os
from unittest.mock import patch, MagicMock

# Ensure parent directory is in the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import debug_subscriber
import config

def test_on_connect():
    mock_client = MagicMock()
    # Call the callback
    debug_subscriber.on_connect(mock_client, None, None, 0, None)
    mock_client.subscribe.assert_called_once_with("swarm/#", qos=1)

@patch('builtins.print')
def test_on_message(mock_print):
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.topic = "swarm/hello"
    mock_message.payload = b"hello payload"
    
    debug_subscriber.on_message(mock_client, None, mock_message)
    mock_print.assert_called_once_with("swarm/hello", "hello payload")

@patch('debug_subscriber.mqtt.Client')
def test_main(mock_client_class):
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance
    
    debug_subscriber.main()
    
    mock_client_class.assert_called_once()
    mock_client_instance.username_pw_set.assert_called_once_with("observer", "demopass")
    # Verify callbacks are hooked
    assert mock_client_instance.on_connect == debug_subscriber.on_connect
    assert mock_client_instance.on_message == debug_subscriber.on_message
    
    mock_client_instance.connect.assert_called_once_with(config.FOXMQ_HOST, config.FOXMQ_PORT)
    mock_client_instance.loop_forever.assert_called_once()
