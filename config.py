GRID_SIZE_X = 10
GRID_SIZE_Y = 10
TOTAL_SECTORS = GRID_SIZE_X * GRID_SIZE_Y

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
