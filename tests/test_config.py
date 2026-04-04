import sys
import os

# Ensure parent directory is in the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config

def test_config_constants():
    """Verify that all configuration constants are defined correctly."""
    assert config.GRID_SIZE_X == 10
    assert config.GRID_SIZE_Y == 10
    assert config.TOTAL_SECTORS == config.GRID_SIZE_X * config.GRID_SIZE_Y
    
    assert config.FOXMQ_HOST == "127.0.0.1"
    assert config.FOXMQ_PORT == 1883
    
    assert config.HEARTBEAT_INTERVAL_SEC == 1.0
    assert config.STALE_TIMEOUT_SEC == 1.5
    assert config.OFFLINE_TIMEOUT_SEC == 3.0
    
    assert config.TOPIC_HELLO == "swarm/hello"
    assert config.TOPIC_HEARTBEAT == "swarm/heartbeat"
    assert config.TOPIC_CLAIM == "swarm/claim"
    assert config.TOPIC_RELEASE == "swarm/release"
    assert config.TOPIC_GRID == "swarm/grid"
