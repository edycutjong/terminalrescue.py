import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
import paho.mqtt.client as mqtt

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

import config

app = FastAPI()

# ──────────────────────────────────────────────────────────────────
#  Global Mesh State
# ──────────────────────────────────────────────────────────────────
drone_status = {}
all_claims = {}
searched_sectors = set()
known_hazards = set()
event_log = []
drone_procs = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send initial state
        await websocket.send_json({
            "type": "INIT_STATE",
            "drone_status": drone_status,
            "all_claims": all_claims,
            "searched_sectors": list(searched_sectors),
            "known_hazards": list(known_hazards),
            "total_sectors": config.TOTAL_SECTORS,
            "grid_x": config.GRID_SIZE_X,
            "grid_y": config.GRID_SIZE_Y
        })

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

# ──────────────────────────────────────────────────────────────────
#  UDP Observer Logic for Vertex Mesh
# ──────────────────────────────────────────────────────────────────
udp_socket = None

def _log_event(event_type: str, text: str):
    ts = time.strftime("%H:%M:%S")
    evt = {"time": ts, "type": event_type, "text": text}
    event_log.append(evt)
    if len(event_log) > 50:
        event_log.pop(0)
    
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast({"type": "EVENT", "data": evt}))
    except RuntimeError:
        asyncio.run(manager.broadcast({"type": "EVENT", "data": evt}))

def start_udp_listener():
    global udp_socket
    import socket
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.bind(("0.0.0.0", 1883))
    
    _log_event("SYSTEM", "Observer bound to Vertex UDP Mesh port 1883")
    
    while True:
        try:
            data, addr = udp_socket.recvfrom(65535)
            payload = json.loads(data.decode("utf-8"))
            msg_type = payload.get("type")
            sender = payload.get("drone_id", payload.get("releasing_drone", "unknown"))

            if msg_type == "HELLO":
                _log_event("HELLO", f"{sender} joined the Vertex mesh")
                drone_status.setdefault(sender, {})
                drone_status[sender]["last_seen"] = time.time()
                drone_status[sender]["status"] = payload.get("status", "READY")
                asyncio.run(manager.broadcast({"type": "DRONE_STATE", "drone_id": sender, "data": drone_status[sender]}))

            elif msg_type == "HEARTBEAT":
                drone_status.setdefault(sender, {})
                if "OFFLINE" in drone_status[sender].get("status", ""):
                    continue

                drone_status[sender]["last_seen"] = time.time()
                drone_status[sender]["status"] = payload.get("status", "UNKNOWN")
                drone_status[sender]["pos"] = payload.get("position")
                drone_status[sender]["claimed"] = payload.get("sectors_claimed", [])
                new_searched = payload.get("sectors_searched", [])
                drone_status[sender]["searched"] = new_searched
                
                updated_searched = False
                for sector in new_searched:
                    if sector not in searched_sectors:
                        searched_sectors.add(sector)
                        updated_searched = True
                        _log_event("SEARCH", f"{sender} searched sector {sector}")

                asyncio.run(manager.broadcast({"type": "DRONE_STATE", "drone_id": sender, "data": drone_status[sender]}))
                if updated_searched:
                    asyncio.run(manager.broadcast({"type": "SEARCHED_SECTORS", "data": list(searched_sectors)}))

            elif msg_type == "CLAIM":
                sector = payload.get("sector")
                if sector and sector not in all_claims:
                    all_claims[sector] = sender
                    _log_event("CLAIM", f"{sender} claimed {sector} via Gossip")
                    asyncio.run(manager.broadcast({"type": "CLAIMS", "data": all_claims}))

            elif msg_type == "RELEASE":
                dead_drone = payload.get("dead_drone")
                released = payload.get("sectors_released", [])
                if dead_drone in drone_status:
                    drone_status[dead_drone]["status"] = "OFFLINE"
                    asyncio.run(manager.broadcast({"type": "DRONE_STATE", "drone_id": dead_drone, "data": drone_status[dead_drone]}))
                
                for s in list(all_claims.keys()):
                    if all_claims.get(s) == dead_drone:
                        del all_claims[s]
                
                _log_event("RELEASE", f"☠ {dead_drone} OFFLINE — {len(released)} sector(s) freed")
                asyncio.run(manager.broadcast({"type": "CLAIMS", "data": all_claims}))

            elif msg_type == "HAZARD":
                sector = payload.get("sector")
                if sector and sector not in known_hazards:
                    known_hazards.add(sector)
                    _log_event("HAZARD", f"⚠️ Sector {sector} designated as HAZARD")
                    asyncio.run(manager.broadcast({"type": "HAZARDS", "data": list(known_hazards)}))

        except Exception as e:
            pass

# ──────────────────────────────────────────────────────────────────
#  Drone Subprocess Management
# ──────────────────────────────────────────────────────────────────
def spawn_drones(count=None):
    count = count or config.DRONE_COUNT
    # Execute the Rust binary instead of the Python mock
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vertex_drone", "target", "release", "vertex_drone")
    
    # Verify binary exists
    if not os.path.exists(script):
        print(f"ERROR: Rust binary not found at {script}. Did you run 'cargo build --release'?")
        return

    for i in range(1, count + 1):
        drone_id = f"drone_{i}"
        proc = subprocess.Popen(
            [script, "--id", drone_id, "--grid", str(config.GRID_SIZE_X), str(config.GRID_SIZE_Y)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        drone_procs[drone_id] = proc
        drone_status[drone_id] = {"status": "CONNECTING", "last_seen": time.time()}

# ──────────────────────────────────────────────────────────────────
#  FastAPI Application
# ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    # Run UDP listener in background thread to avoid blocking asyncio
    import threading
    t = threading.Thread(target=start_udp_listener, daemon=True)
    t.start()
    
    # Spawn Rust drones (unless disabled for standalone environments like docker-compose)
    if os.environ.get("NO_SPAWN") != "1":
        spawn_drones()
    
    # Track dead drones
    async def stale_checker():
        while True:
            now = time.time()
            for d_id, d_info in list(drone_status.items()):
                 if "OFFLINE" not in d_info.get("status", ""):
                     if now - d_info.get("last_seen", now) > 5.0:
                         d_info["status"] = "OFFLINE"
                         for s in list(all_claims.keys()):
                             if all_claims.get(s) == d_id:
                                 del all_claims[s]
                         await manager.broadcast({"type": "DRONE_STATE", "drone_id": d_id, "data": d_info})
                         await manager.broadcast({"type": "CLAIMS", "data": all_claims})
            await asyncio.sleep(1)
    
    asyncio.create_task(stale_checker())

@app.on_event("shutdown")
def shutdown_event():
    for drone_id, proc in drone_procs.items():
        if proc.poll() is None:
            proc.terminate()
    if udp_socket:
        udp_socket.close()


@app.get("/")
def get_index():
    with open("static/index.html", "r") as f:
         content = f.read()
    return HTMLResponse(content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming commands from frontend
            msg = json.loads(data)
            if msg.get("action") == "KILL":
                d_id = msg.get("drone_id")
                if d_id in drone_procs:
                    proc = drone_procs[d_id]
                    if proc.poll() is None:
                        proc.terminate()
                        _log_event("SYSTEM", f"Manually killed {d_id}")
            elif msg.get("action") == "HAZARD":
                sector = msg.get("sector")
                if udp_socket:
                    hazard_msg = {"type": "HAZARD", "sector": sector, "timestamp_ms": int(time.time()*1000)}
                    udp_socket.sendto(json.dumps(hazard_msg).encode("utf-8"), ("255.255.255.255", 1883))
            elif msg.get("action") == "START":
                if udp_socket:
                    start_msg = {"type": "SYSTEM", "action": "START", "timestamp_ms": int(time.time()*1000)}
                    udp_socket.sendto(json.dumps(start_msg).encode("utf-8"), ("255.255.255.255", 1883))
                    _log_event("SYSTEM", "MISSION START signal broadcasted")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("web_ui:app", host="0.0.0.0", port=8000, reload=True)
