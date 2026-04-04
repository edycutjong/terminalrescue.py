#!/usr/bin/env python3
import time
import json
import uuid
import sys
import argparse
from typing import Dict, List, Set, Optional
import paho.mqtt.client as mqtt

import config

class DroneNode:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.peers: Dict[str, float] = {}  # drone_id -> last_seen_timestamp
        
        # Grid state
        self.claimed_sectors: Set[str] = set()
        self.searched_sectors: Set[str] = set()
        self.global_searched_sectors: Set[str] = set()
        self.all_claims: Dict[str, str] = {}  # sector -> drone_id
        self.pending_claims: Set[str] = set()
        
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, 
            client_id=f"{self.node_id}_{uuid.uuid4().hex[:6]}",
            protocol=mqtt.MQTTv5
        )
        self.client.username_pw_set(self.node_id, "demopass") # FoxMQ user authentication
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.state = "CONNECTING"
        self.current_pos = {"x": 0, "y": 0}

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[{self.node_id}] Connected to FoxMQ successfully!")
            self.state = "READY"
            
            # Subscribe to all swarm topics
            self.client.subscribe("swarm/#", qos=1)
            
            # Broadcast HELLO
            self.publish_hello()
        else:
            print(f"[{self.node_id}] Connection failed: {reason_code}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        print(f"[{self.node_id}] Disconnected.")

    def on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode('utf-8'))
            msg_type = payload.get("type")
            sender = payload.get("drone_id", payload.get("releasing_drone", "unknown"))

            if sender == self.node_id:
                if msg_type in ("HELLO", "HEARTBEAT", "RELEASE"):
                    return
                # We process our own CLAIM messages to enforce global BFT ordering.
                
            if msg_type == "HELLO":
                print(f"[{self.node_id}] Discovered peer: {sender}")
                self.peers[sender] = time.time()
                
            elif msg_type == "HEARTBEAT":
                self.peers[sender] = time.time()
                for s in payload.get("sectors_searched", []):
                    self.global_searched_sectors.add(s)
                # Sync claims from heartbeat — critical for late-joining drones
                # (MQTT doesn't replay old CLAIM messages to new subscribers)
                for s in payload.get("sectors_claimed", []):
                    if s not in self.all_claims:
                        self.all_claims[s] = sender
                
            elif msg_type == "CLAIM":
                sector = payload.get("sector")
                self.pending_claims.discard(sector)
                # BFT Consensus: first claim processed wins (globally ordered by FoxMQ)
                if sector not in self.all_claims:
                    self.all_claims[sector] = sender
                    if sender == self.node_id:
                        self.claimed_sectors.add(sector)
                    print(f"[{self.node_id}] Acknowledged {sender} claimed {sector}")
                elif sender == self.node_id and self.all_claims[sector] != self.node_id:
                    # Our claim was rejected — someone else got it first via BFT
                    print(f"[{self.node_id}] Claim for {sector} rejected — owned by {self.all_claims[sector]}")
                    
            elif msg_type == "RELEASE":
                dead_drone = payload.get("dead_drone")
                released = payload.get("sectors_released", [])
                print(f"[{self.node_id}] Received RELEASE for dead drone {dead_drone} by {sender}")
                if dead_drone in self.peers:
                    del self.peers[dead_drone]
                for s in released:
                    if self.all_claims.get(s) == dead_drone:
                        del self.all_claims[s]
                    # Also drop from our own claimed set if the dead drone stole them
                    self.claimed_sectors.discard(s)
                # Trigger re-claim logic later

        except Exception as e:
            print(f"Error parsing message: {e}")

    def publish_hello(self):
        msg = {
            "type": "HELLO",
            "drone_id": self.node_id,
            "timestamp_ms": int(time.time() * 1000),
            "capabilities": ["search", "rescue"],
            "status": "READY"
        }
        self.client.publish(config.TOPIC_HELLO, json.dumps(msg), qos=1)

    def publish_heartbeat(self):
        msg = {
            "type": "HEARTBEAT",
            "drone_id": self.node_id,
            "timestamp_ms": int(time.time() * 1000),
            "position": self.current_pos,
            "sectors_claimed": list(self.claimed_sectors),
            "sectors_searched": list(self.searched_sectors),
            "status": self.state
        }
        self.client.publish(config.TOPIC_HEARTBEAT, json.dumps(msg), qos=1)

    def publish_claim(self, sector: str):
        # We publish a claim. If we receive it and it wasn't claimed yet, it's ours.
        msg = {
            "type": "CLAIM",
            "drone_id": self.node_id,
            "sector": sector,
            "timestamp_ms": int(time.time() * 1000),
            "priority": 0.5 # Simplified priority
        }
        self.client.publish(config.TOPIC_CLAIM, json.dumps(msg), qos=1)

    def publish_release(self, dead_drone: str, sectors: List[str]):
        msg = {
            "type": "RELEASE",
            "releasing_drone": self.node_id,
            "dead_drone": dead_drone,
            "sectors_released": sectors,
            "timestamp_ms": int(time.time() * 1000)
        }
        self.client.publish(config.TOPIC_RELEASE, json.dumps(msg), qos=1)

    def check_peers(self):
        now = time.time()
        dead_peers = []
        for peer_id, last_seen in list(self.peers.items()):
            if now - last_seen > config.OFFLINE_TIMEOUT_SEC:
                print(f"[{self.node_id}] DETECTED {peer_id} OFFLINE! Releasing their sectors.")
                dead_peers.append(peer_id)
        
        for dead in dead_peers:
            # Find sectors claimed by dead drone
            dead_sectors = [s for s, d in self.all_claims.items() if d == dead]
            self.publish_release(dead, dead_sectors)
            del self.peers[dead]

    def bid_for_sectors(self):
        # Sort peers to agree on consistent identical list
        all_nodes = list(self.peers.keys()) + [self.node_id]
        all_nodes.sort()
        
        # Use a shared seed derived from the participant list, so all drones
        # independently calculate the EXACT SAME random assignment map!
        import random
        rng = random.Random(",".join(all_nodes))

        # Generate all 100 sectors and shuffle them
        all_sectors = [f"{x}_{y}" for y in range(config.GRID_SIZE_Y) for x in range(config.GRID_SIZE_X)]
        rng.shuffle(all_sectors)

        # Build an initial owner list ensuring each drone gets at least 1 sector
        owners = list(all_nodes)
        
        # Randomly assign the remaining 95 sectors
        remaining_count = config.TOTAL_SECTORS - len(owners)
        for _ in range(remaining_count):
            owners.append(rng.choice(all_nodes))

        # We now have exactly 100 owners, corresponding to all_sectors
        my_assigned_sectors = [
            all_sectors[i] for i in range(len(all_sectors)) if owners[i] == self.node_id
        ]
        my_fair_share = len(my_assigned_sectors)
        
        # Add remaining sectors as fallback to guarantee 100% grid completion seamlessly
        other_sectors = [s for s in all_sectors if s not in my_assigned_sectors]
        search_sequence = my_assigned_sectors + other_sectors

        claimed_this_round = 0
        for sector in search_sequence:
            if sector not in self.all_claims:
                self.publish_claim(sector)
                self.pending_claims.add(sector)
                claimed_this_round += 1
                time.sleep(0.05)  # faster claiming because a drone might have up to 40 sectors

                if claimed_this_round % 4 == 0:
                    self.publish_heartbeat()

                if claimed_this_round >= my_fair_share:
                    break

        self.publish_heartbeat()

    def run(self):
        print(f"Starting {self.node_id}...")
        connected = False
        while not connected:
            try:
                self.client.connect(config.FOXMQ_HOST, config.FOXMQ_PORT, 60)
                connected = True
            except (ConnectionRefusedError, OSError) as e:
                print(f"[{self.node_id}] ⏳ Waiting for FoxMQ broker... ({e})")
                time.sleep(2)
        self.client.loop_start()

        last_heartbeat = 0
        try:
            while True:
                now = time.time()
                
                if self.state == "READY":
                    # Wait for up to 3s OR for 5 drones to join the mesh before claiming.
                    # This ensures beautiful, orderly sector assignment based on mesh rank.
                    if not hasattr(self, '_ready_since'):
                        self._ready_since = now
                    
                    if len(self.peers) >= 4 or (now - self._ready_since >= 3.0):
                        self.state = "CLAIMING"
                
                if self.state == "CLAIMING":
                    self.bid_for_sectors()
                    # Wait for BFT to confirm/reject our claims
                    time.sleep(0.5)
                    # Clean up: remove sectors we claimed but BFT gave to others
                    rejected = set()
                    for s in list(self.claimed_sectors):
                        if self.all_claims.get(s) != self.node_id:
                            rejected.add(s)
                    self.claimed_sectors -= rejected
                    
                    if len(self.all_claims) >= config.TOTAL_SECTORS:
                        self.state = "SEARCHING"
                    else:
                        # If the grid isn't 100% claimed yet, stay in CLAIMING
                        # to continuously aggressively sweep the remaining orphaned pieces!
                        pass
                
                if self.state == "SEARCHING":
                    # Simulate searching
                    if self.claimed_sectors:
                        sector_to_search = list(self.claimed_sectors - self.global_searched_sectors)
                        if sector_to_search:
                            # Sort properly by Y then X to make searching sequential and non-random
                            sector_to_search.sort(key=lambda s: (int(s.split('_')[1]), int(s.split('_')[0])))
                            target = sector_to_search[0]
                            time.sleep(1) # Simulated delay
                            self.searched_sectors.add(target)
                            self.global_searched_sectors.add(target)
                            
                            parts = target.split("_")
                            self.current_pos = {"x": int(parts[0]), "y": int(parts[1])}
                            print(f"[{self.node_id}] Searched sector {target}")
                        else:
                            # Done with our sectors — check if grid is fully covered
                            total_claimed = len(self.all_claims)
                            if total_claimed < config.TOTAL_SECTORS:
                                # Unclaimed sectors remain — go claim more
                                self.state = "CLAIMING"
                            else:
                                self.state = "COMPLETE"
                    else:
                        # No sectors at all — try claiming again if grid isn't full
                        if len(self.all_claims) < config.TOTAL_SECTORS:
                            self.state = "CLAIMING"
                        else:
                            self.state = "COMPLETE"

                # Periodic tasks
                if now - last_heartbeat > config.HEARTBEAT_INTERVAL_SEC:
                    self.publish_heartbeat()
                    self.check_peers()
                    last_heartbeat = now
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, required=True, help="Unique Drone ID")
    args = parser.parse_args()
    
    drone = DroneNode(args.id)
    drone.run()
