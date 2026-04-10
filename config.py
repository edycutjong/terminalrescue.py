import os

GRID_SIZE_X = int(os.environ.get("GRID_X", 10))
GRID_SIZE_Y = int(os.environ.get("GRID_Y", 10))
TOTAL_SECTORS = GRID_SIZE_X * GRID_SIZE_Y
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 5))

FOXMQ_HOST = "127.0.0.1"
FOXMQ_PORT = 1883

HEARTBEAT_INTERVAL_SEC = 1.0  # fast updates for live dashboard
STALE_TIMEOUT_SEC = 1.5       # How long without heartbeat before marking stale
OFFLINE_TIMEOUT_SEC = 3.0     # How long without heartbeat before marking offline and releasing sectors

# MQTT Topics
TOPIC_HELLO = "swarm/hello"
TOPIC_HEARTBEAT = "swarm/heartbeat"
TOPIC_CLAIM = "swarm/claim"
TOPIC_RELEASE = "swarm/release"
TOPIC_GRID = "swarm/grid"
TOPIC_HAZARD = "swarm/hazard"

SEARCH_DELAY_SEC = 1.0
HAZARD_DELAY_SEC = 3.0
