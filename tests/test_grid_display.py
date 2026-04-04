import sys
import os
import json
import time
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import grid_display
import config

class StopLoop(Exception): pass

def test_speak():
    with patch('sys.platform', 'darwin'), patch('subprocess.Popen') as mock_popen:
        grid_display.speak("Hello")
        mock_popen.assert_called_once()
        
    with patch('sys.platform', 'linux'), patch('subprocess.Popen') as mock_popen:
        grid_display.speak("Hello")
        mock_popen.assert_not_called()

@patch('grid_display.mqtt.Client')
def test_observer_init(mock_mqtt):
    obs = grid_display.ObserverNode()
    assert obs.node_id == "observer"
    mock_mqtt.return_value.username_pw_set.assert_called_with("observer", "demopass")

@patch('grid_display.mqtt.Client')
def test_on_connect(mock_mqtt):
    obs = grid_display.ObserverNode()
    obs.on_connect(obs.client, None, None, 0, None)
    obs.client.subscribe.assert_called_with("swarm/#", qos=1)
    
    obs.client.subscribe.reset_mock()
    obs.on_connect(obs.client, None, None, 1, None)
    obs.client.subscribe.assert_not_called()

@patch('grid_display.speak')
@patch('grid_display.mqtt.Client')
def test_on_message(mock_mqtt, mock_speak):
    obs = grid_display.ObserverNode()
    
    # HELLO
    msg = MagicMock()
    msg.payload = json.dumps({"type": "HELLO", "drone_id": "drone_1", "status": "READY"}).encode('utf-8')
    obs.on_message(obs.client, None, msg)
    assert "drone_1" in obs.drone_status
    assert obs.drone_status["drone_1"]["status"] == "READY"

    # HEARTBEAT
    msg.payload = json.dumps({"type": "HEARTBEAT", "drone_id": "drone_1", "status": "SEARCHING", "position": {"x": 5, "y": 5}, "sectors_searched": ["0_0", "5_5"]}).encode('utf-8')
    obs.on_message(obs.client, None, msg)
    assert obs.drone_status["drone_1"]["status"] == "SEARCHING"
    assert "5_5" in obs.searched_sectors
    
    # HEARTBEAT IGNORING OFFLINE
    obs.drone_status["drone_2"] = {"status": "OFFLINE"}
    msg.payload = json.dumps({"type": "HEARTBEAT", "drone_id": "drone_2", "status": "SEARCHING"}).encode('utf-8')
    obs.on_message(obs.client, None, msg)
    assert obs.drone_status["drone_2"]["status"] == "OFFLINE"

    # CLAIM
    msg.payload = json.dumps({"type": "CLAIM", "drone_id": "drone_1", "sector": "1_1"}).encode('utf-8')
    obs.on_message(obs.client, None, msg)
    assert obs.all_claims["1_1"] == "drone_1"
    
    # CLAIM triggering start pattern if == TOTAL_SECTORS
    obs.start_time = None
    saved_claims = obs.all_claims.copy()
    obs.all_claims = {f"{x}_{y}": "drone_1" for x in range(10) for y in range(10) if f"{x}_{y}" != "2_2"}
    msg.payload = json.dumps({"type": "CLAIM", "drone_id": "drone_1", "sector": "2_2"}).encode('utf-8')
    obs.on_message(obs.client, None, msg)
    assert obs.start_time is not None
    mock_speak.assert_called_with("Swarm bootup complete. Initial grid locked. Commencing decentralized search.")
    
    # RELEASE
    obs.all_claims["2_2"] = "drone_2"
    msg.payload = json.dumps({"type": "RELEASE", "releasing_drone": "drone_1", "dead_drone": "drone_2", "sectors_released": ["2_2"]}).encode('utf-8')
    obs.on_message(obs.client, None, msg)
    assert "2_2" not in obs.all_claims
    assert obs.drone_status["drone_2"]["status"] == "OFFLINE"

    # INVALID JSON
    msg.payload = b"not json"
    obs.on_message(obs.client, None, msg) 

@patch('grid_display.mqtt.Client')
def test_render_event_log(mock_mqtt):
    obs = grid_display.ObserverNode()
    # Empty
    panel = obs._render_event_log()
    assert panel is not None
    
    # Event log 
    obs._log_event("TEST", "test", "red")
    panel = obs._render_event_log()
    assert panel is not None

@patch('grid_display.speak')
@patch('grid_display.mqtt.Client')
def test_render_progress(mock_mqtt, mock_speak):
    obs = grid_display.ObserverNode()
    # Not done
    obs.searched_sectors = {"0_0"}
    obs._render_progress()
    mock_speak.assert_not_called()

    # Done
    config.TOTAL_SECTORS = 100
    obs.searched_sectors = {f"{x}_{y}" for x in range(10) for y in range(10)}
    obs.mission_complete_announced = False
    obs._render_progress()
    obs._render_progress() # Call twice to test mission_complete_announced flag

@patch('grid_display.time.time', return_value=1000)
@patch('grid_display.mqtt.Client')
def test_render_telemetry(mock_mqtt, mock_time):
    obs = grid_display.ObserverNode()
    obs.drone_status["drone_1"] = {"status": "OFFLINE", "last_seen": 990}
    obs.drone_status["drone_2"] = {"status": "SEARCHING", "last_seen": 999}
    obs.drone_status["drone_3"] = {"status": "CLAIMING", "last_seen": 990}
    obs.drone_status["drone_4"] = {"status": "READY", "last_seen": 900} # age > 15s
    obs.all_claims["0_0"] = "drone_2"
    obs._render_telemetry()

@patch('grid_display.time.time', return_value=1000)
@patch('grid_display.mqtt.Client')
def test_render_grid(mock_mqtt, mock_time):
    obs = grid_display.ObserverNode()
    obs.searched_sectors = {"0_0"}
    obs.all_claims = {"1_1": "drone_1", "1_2": "drone_2", "1_3": "drone_unknown"}
    obs.drone_status["drone_1"] = {"status": "SEARCHING", "pos": {"x": 1, "y": 1}}
    obs.drone_status["drone_2"] = {"status": "OFFLINE", "pos": {"x": 1, "y": 2}}
    obs._render_grid()

@patch('grid_display.time.time', side_effect=[1000, 1065])
@patch('grid_display.mqtt.Client')
def test_build_title(mock_mqtt, mock_time):
    obs = grid_display.ObserverNode()
    obs.start_time = None
    obs._build_title()
    
    obs.start_time = 1000
    obs.drone_status["drone_1"] = {"status": "READY"}
    obs._build_title()

@patch('grid_display.time.sleep')
@patch('grid_display.subprocess.Popen')
@patch('grid_display.mqtt.Client')
def test_spawn_kill_cleanup_drones(mock_mqtt, mock_popen, mock_sleep):
    obs = grid_display.ObserverNode()
    obs._spawn_drones(2)
    assert len(obs.drone_procs) == 2

    # Kill first drone
    mock_proc1 = MagicMock()
    mock_proc1.poll.return_value = None
    mock_proc2 = MagicMock()
    mock_proc2.poll.return_value = 1  # already dead
    obs.drone_procs = [("drone_1", mock_proc2), ("drone_2", mock_proc1)]
    
    label = obs._kill_next_drone()
    assert label == "BRAVO"

    # Cleanup
    # Proc2 already dead, proc1 still alive so terminate() called
    obs._cleanup_drones()
    mock_proc1.terminate.assert_called()

    # What if wait fails?
    mock_proc1.wait.side_effect = Exception("failed wait")
    obs._cleanup_drones()
    mock_proc1.kill.assert_called()
    
    # Return none from kill if none alive
    mock_proc1.poll.return_value = 1
    assert obs._kill_next_drone() is None

@patch('grid_display.sys.stdin')
@patch('grid_display.termios.tcgetattr')
@patch('grid_display.termios.tcsetattr')
@patch('grid_display.tty.setcbreak')
@patch('grid_display.mqtt.Client')
def test_key_listener(mock_mqtt, mock_tty, mock_tcsetattr, mock_tcgetattr, mock_stdin):
    obs = grid_display.ObserverNode()
    
    # Provide characters 'k', 'K', 'q'
    mock_stdin.fileno.return_value = 0
    mock_stdin.read.side_effect = ['a', 'k', 'K', 'q']
    
    obs._key_listener()
    assert obs.kill_requested == True
    assert obs.quit_requested == True

    # Test Exception in tty
    mock_tty.side_effect = Exception("error")
    obs.quit_requested = False
    obs._key_listener()
    assert obs.quit_requested == False

@patch('grid_display.threading.Thread')
@patch('rich.live.Live')
@patch('rich.console.Console')
@patch('grid_display.time.sleep')
@patch('grid_display.time.time')
@patch('grid_display.mqtt.Client')
def test_run(mock_mqtt, mock_time, mock_sleep, mock_console, mock_live, mock_thread):
    obs = grid_display.ObserverNode()
    obs.client.connect.side_effect = [ConnectionRefusedError("fail"), None]
    
    def fake_time():
        return 1000

    def fake_render_grid():
        if obs._run_iterations == 0:
            obs._run_iterations += 1
            obs.kill_requested = True
            return ""
        if obs._run_iterations == 1:
            obs._run_iterations += 1
            return ""
        obs.quit_requested = True
        return ""

    obs._run_iterations = 0
    obs._render_grid = fake_render_grid
    
    obs.drone_status["drone_1"] = {"status": "READY", "last_seen": 900}
    obs.all_claims["1_1"] = "drone_1"
    mock_time.side_effect = fake_time
    
    obs.run()

    # Keyboard interrupt handler
    obs.client.connect.side_effect = None
    obs.client.connect.return_value = None
    mock_sleep.side_effect = KeyboardInterrupt
    obs.quit_requested = False
    obs.run()
