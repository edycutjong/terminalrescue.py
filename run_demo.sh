#!/bin/bash

# run_demo.sh
# One-command launcher: Vertex Mesh Mission Control
# Drones are spawned as native Rust binaries by the observer process.

set -e

clear
echo -ne "\033]0;Terminal Rescue - Vertex Mesh Simulation\007"

echo -e "\033[1;36m"
cat << 'EOF'
 ╔═══════════════════════════════════════════════════════════════════════════════════╗
 ║  _______                  _             _   _____                                 ║
 ║ |__   __|                (_)           | | |  __ \                                ║
 ║    | | ___ _ __ _ __ ___  _ _ __   __ _| | | |__) |___  ___  ___  _   _  ___      ║
 ║    | |/ _ \ '__| '_ ` _ \| | '_ \ / _` | | |  _  // _ \/ __|/ __|| | | |/ _ \     ║
 ║    | |  __/ |  | | | | | | | | | | (_| | | | | \ \  __/\__ \ (__ | |_| |  __/     ║
 ║    |_|\___|_|  |_| |_| |_|_|_| |_|\__,_|_| |_|  \_\___||___/\___| \__,_|\___|     ║
 ║                                                                                   ║
 ║                       V e r t e x   R u s t   S i m u l a t i o n                 ║
 ╚═══════════════════════════════════════════════════════════════════════════════════╝
EOF
echo -e "\033[0m"

if [ -f "venv/bin/python" ]; then
    PYTHON_BIN="venv/bin/python"
else
    PYTHON_BIN="python3"
fi

if [ ! -f "vertex_drone/target/release/vertex_drone" ]; then
    echo "❌ Error: Vertex Rust binary not found."
    echo "Please run: make setup"
    exit 1
fi

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  Press K to kill a drone  │  Q to quit     ║"
echo "╚════════════════════════════════════════════╝"
echo ""
sleep 1

# ── Launch Mission Control ───────────────────────────────────────
(
    sleep 2
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open "http://localhost:8000"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        xdg-open "http://localhost:8000"
    fi
) &

$PYTHON_BIN -m uvicorn web_ui:app --host 0.0.0.0 --port 8000
