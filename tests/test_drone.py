import sys
import os
import json
import time
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import drone
import config

class StopLoopException(Exception): pass

@patch('drone.mqtt.Client')
def test_drone_init(mock_mqtt):
    d = drone.DroneNode("alpha")
    assert d.node_id == "alpha"
    assert d.state == "CONNECTING"
    mock_mqtt.return_value.username_pw_set.assert_called_with("alpha", "demopass")

@patch('drone.mqtt.Client')
def test_on_connect(mock_mqtt):
    d = drone.DroneNode("alpha")
    # connect success
    d.publish_hello = MagicMock()
    d.on_connect(d.client, None, None, 0, None)
    assert d.state == "READY"
    d.client.subscribe.assert_called_with("swarm/#", qos=1)
    d.publish_hello.assert_called_once()
    
    # connect fail
    d.state = "CONNECTING"
    d.on_connect(d.client, None, None, 1, None)
    assert d.state == "CONNECTING" # untouched

@patch('builtins.print')
@patch('drone.mqtt.Client')
def test_on_disconnect(mock_mqtt, mock_print):
    d = drone.DroneNode("alpha")
    d.on_disconnect(d.client, None, None, 0, None)
    mock_print.assert_called_with("[alpha] Disconnected.")

@patch('drone.mqtt.Client')
def test_on_message(mock_mqtt):
    d = drone.DroneNode("alpha")
    
    # Test own message ignored
    msg = MagicMock()
    msg.payload = json.dumps({"type": "HELLO", "drone_id": "alpha"}).encode('utf-8')
    d.on_message(d.client, None, msg)
    assert len(d.peers) == 0

    # Test HELLO
    msg.payload = json.dumps({"type": "HELLO", "drone_id": "beta"}).encode('utf-8')
    d.on_message(d.client, None, msg)
    assert "beta" in d.peers

    # Test HEARTBEAT
    msg.payload = json.dumps({
        "type": "HEARTBEAT", "drone_id": "beta", 
        "sectors_searched": ["0_0"], "sectors_claimed": ["0_1"]
    }).encode('utf-8')
    d.on_message(d.client, None, msg)
    assert "0_0" in d.global_searched_sectors
    assert d.all_claims["0_1"] == "beta"

    # Test CLAIM
    msg.payload = json.dumps({"type": "CLAIM", "drone_id": "beta", "sector": "0_2"}).encode('utf-8')
    d.pending_claims.add("0_2")
    d.on_message(d.client, None, msg)
    assert "0_2" not in d.pending_claims
    assert d.all_claims["0_2"] == "beta"
    
    # Test our own claim accepted
    msg.payload = json.dumps({"type": "CLAIM", "drone_id": "alpha", "sector": "0_3"}).encode('utf-8')
    d.on_message(d.client, None, msg)
    assert "0_3" in d.all_claims
    assert d.all_claims["0_3"] == "alpha"
    assert "0_3" in d.claimed_sectors

    # Test our claim rejected
    d.all_claims["0_4"] = "beta"
    msg.payload = json.dumps({"type": "CLAIM", "drone_id": "alpha", "sector": "0_4"}).encode('utf-8')
    d.on_message(d.client, None, msg)
    assert d.all_claims["0_4"] == "beta"

    # Test RELEASE
    d.all_claims["0_5"] = "gamma"
    d.peers["gamma"] = 1234
    msg.payload = json.dumps({
        "type": "RELEASE", "releasing_drone": "beta", 
        "dead_drone": "gamma", "sectors_released": ["0_5"]
    }).encode('utf-8')
    d.on_message(d.client, None, msg)
    assert "gamma" not in d.peers
    assert "0_5" not in d.all_claims

    # Test message exception
    msg.payload = b"invalid json"
    d.on_message(d.client, None, msg) # should catch and ignore silently or print


@patch('drone.time.time', return_value=1000)
@patch('drone.mqtt.Client')
def test_publishers(mock_mqtt, mock_time):
    d = drone.DroneNode("alpha")
    d.current_pos = {"x": 5, "y": 5}
    d.state = "READY"
    
    d.publish_hello()
    d.client.publish.assert_called_with(config.TOPIC_HELLO, json.dumps({
        "type": "HELLO", "drone_id": "alpha", "timestamp_ms": 1000000,
        "capabilities": ["search", "rescue"], "status": "READY"
    }), qos=1)

    d.publish_heartbeat()
    d.client.publish.assert_called_with(config.TOPIC_HEARTBEAT, json.dumps({
        "type": "HEARTBEAT", "drone_id": "alpha", "timestamp_ms": 1000000,
        "position": {"x": 5, "y": 5}, "sectors_claimed": [], "sectors_searched": [], "status": "READY"
    }), qos=1)

    d.publish_claim("1_1")
    d.client.publish.assert_called_with(config.TOPIC_CLAIM, json.dumps({
        "type": "CLAIM", "drone_id": "alpha", "sector": "1_1",
        "timestamp_ms": 1000000, "priority": 0.5
    }), qos=1)

    d.publish_release("beta", ["2_2"])
    d.client.publish.assert_called_with(config.TOPIC_RELEASE, json.dumps({
        "type": "RELEASE", "releasing_drone": "alpha", "dead_drone": "beta",
        "sectors_released": ["2_2"], "timestamp_ms": 1000000
    }), qos=1)


@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_check_peers(mock_mqtt, mock_time):
    d = drone.DroneNode("alpha")
    mock_time.return_value = 100
    d.peers["beta"] = 100 - config.OFFLINE_TIMEOUT_SEC - 1
    d.all_claims["9_9"] = "beta"
    
    d.publish_release = MagicMock()
    d.check_peers()
    d.publish_release.assert_called_with("beta", ["9_9"])
    assert "beta" not in d.peers

@patch('drone.time.sleep')
@patch('drone.mqtt.Client')
def test_bid_for_sectors(mock_mqtt, mock_sleep):
    d = drone.DroneNode("alpha")
    d.peers["beta"] = 123
    d.publish_claim = MagicMock()
    d.publish_heartbeat = MagicMock()
    
    d.bid_for_sectors()
    # verify it attempted to claim ~50 sectors
    assert d.publish_claim.call_count > 0
    assert len(d.pending_claims) > 0


def make_fake_time():
    t = 100
    def fake_time():
        nonlocal t
        t += 1
        if t > 110:
            raise StopLoopException()
        return t
    return fake_time

@patch('drone.time.sleep')
@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_run_connection_retry(mock_mqtt, mock_time, mock_sleep):
    d = drone.DroneNode("alpha")
    d.client.connect.side_effect = [ConnectionRefusedError("fail"), None]
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass

@patch('drone.time.sleep')
@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_run_state_machine_ready(mock_mqtt, mock_time, mock_sleep):
    d = drone.DroneNode("alpha")
    d.state = "READY"
    d.client.connect.return_value = None
    
    # Test time-based transition
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state != "READY"  # It will transition to CLAIMING and possibly SEARCHING

    # Test peer-based transition
    d = drone.DroneNode("alpha")
    d.state = "READY"
    d.client.connect.return_value = None
    d.peers = {"1":0,"2":0,"3":0,"4":0}
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state != "READY"

@patch('drone.time.sleep')
@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_run_state_machine_complete(mock_mqtt, mock_time, mock_sleep):
    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.state = "COMPLETE"
    d.all_claims = {} 
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state != "COMPLETE"

@patch('drone.time.sleep')
@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_run_state_machine_claiming(mock_mqtt, mock_time, mock_sleep):
    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.state = "CLAIMING"
    d.bid_for_sectors = MagicMock()
    d.claimed_sectors = {"0_0", "0_1"}
    d.all_claims = {"0_0": "alpha"} 
    
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    
    assert "0_1" not in d.claimed_sectors
    
    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.all_claims = {f"{x}_{y}": "alpha" for x in range(10) for y in range(10)}
    d.state = "CLAIMING"
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state == "COMPLETE"

@patch('drone.time.sleep')
@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_run_state_machine_searching(mock_mqtt, mock_time, mock_sleep):
    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    
    d.state = "SEARCHING"
    d.claimed_sectors = {"0_0", "1_1"}
    d.global_searched_sectors = set()
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert "0_0" in d.searched_sectors

    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.state = "SEARCHING"
    d.claimed_sectors = {"0_0"}
    d.global_searched_sectors = {"0_0"}
    d.all_claims = {f"{x}_{y}": "alpha" for x in range(10) for y in range(10)}
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state == "COMPLETE"
    
    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.state = "SEARCHING"
    d.all_claims = {}
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state == "CLAIMING"

    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.state = "SEARCHING"
    d.claimed_sectors = set()
    d.all_claims = {f"{x}_{y}": "alpha" for x in range(10) for y in range(10)}
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state == "COMPLETE"

    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    d.state = "SEARCHING"
    d.claimed_sectors = set()
    d.all_claims = {}
    mock_time.side_effect = make_fake_time()
    try: d.run()
    except StopLoopException: pass
    assert d.state == "CLAIMING"

@patch('builtins.print')
@patch('drone.time.sleep')
@patch('drone.time.time')
@patch('drone.mqtt.Client')
def test_run_keyboard_interrupt(mock_mqtt, mock_time, mock_sleep, mock_print):
    d = drone.DroneNode("alpha")
    d.client.connect.return_value = None
    mock_time.side_effect = KeyboardInterrupt
    d.run()
    mock_print.assert_any_call("Shutting down...")
    d.client.disconnect.assert_called_once()
