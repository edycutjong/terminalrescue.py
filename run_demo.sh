#!/bin/bash

# run_demo.sh
# One-command launcher: FoxMQ broker → fullscreen Mission Control
# Drones are spawned by the observer process. No tmux needed.

set -e

if ! python3 -c "import paho.mqtt" &> /dev/null; then
    echo "❌ Error: Python dependencies are missing."
    echo "Please run: pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "./foxmq" ]; then
    echo "❌ Error: FoxMQ binary not found."
    echo "Please run: ./setup_foxmq.sh"
    exit 1
fi

# ── Start FoxMQ broker in background ─────────────────────────────
echo "🚀 Starting FoxMQ broker..."
./foxmq run --secret-key-file=foxmq.d/key_0.pem &
FOXMQ_PID=$!
sleep 2

if ! kill -0 $FOXMQ_PID 2>/dev/null; then
    echo "❌ FoxMQ broker failed to start."
    exit 1
fi
echo "✅ FoxMQ broker running (PID: $FOXMQ_PID)"
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  Press K to kill a drone  │  Q to quit     ║"
echo "╚════════════════════════════════════════════╝"
echo ""
sleep 1

# ── Cleanup trap — kill broker on exit ───────────────────────────
cleanup() {
    echo ""
    echo "🛑 Stopping FoxMQ broker (PID: $FOXMQ_PID)..."
    kill $FOXMQ_PID 2>/dev/null
    wait $FOXMQ_PID 2>/dev/null
    echo "✅ Cleanup complete."
}
trap cleanup EXIT

# ── Launch Mission Control ───────────────────────────────────────
python3 grid_display.py
