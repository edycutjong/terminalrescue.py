# Terminal Rescue - Voiceover Scripts

Use these scripts with ElevenLabs (recommended voices: *Marcus* for deep/technical or *Adam* for clear/energetic narrative) to narrate over the two demonstration videos.

---

## 🎬 Video 1: The Kill-Switch Stunt (terminal-rescue-demo.webm)
*Approx 35-40 seconds of audio. Read with a steady, confident pace.*

**[0:00 - Swarm Bootup]**
"Welcome to Terminal Rescue. What you're seeing is a live, leaderless drone swarm powered by native Rust binaries and the Tashi FoxMQ broker."

**[0:08 - Mesh Stabilization]**
"Each drone computes its own optimal search vector to map the grid without relying on any central command server."

**[0:15 - Kill-Switch Activation]**
"To prove the resilience of our Vertex Byzantine Fault Tolerance, let's trigger the Kill-Switch and forcefully take down a drone mid-flight."

**[0:20 - Fault Detection & Recovery]**
"Instantly, the surrounding mesh detects the missing heartbeat. The dead node's claimed sectors are released back to the network, and surviving drones immediately re-bid and redirect their flight paths to cover the gap."

**[0:30 - Mission Complete]**
"Zero collisions. Zero double-searching. One hundred percent autonomous recovery."

---

## 🚧 Video 2: Dynamic Hazard Avoidance (hazard-avoidance-demo.webm)
*Approx 15-20 seconds of audio. Read with slightly faster urgency.*

**[0:00 - Setup & Dropping Hazards]**
"In real-world operations, environments change rapidly. You can dynamically click on the grid to drop impassable hazard zones in real-time."

**[0:06 - Trajectory Rerouting]**
"The Rust backend instantly broadcasts a massive geometric cost-penalty. Watch as the drones' native pathfinding algorithms instinctively redraw their flight vectors mid-air, snaking perfectly around the danger zone without losing coordination."

---

### Tips for ElevenLabs Generation:
- Add slight pauses like `[pause]` or `-` to align the audio perfectly with the visual actions (like right before you say "let's trigger the Kill-Switch").
- Use the **"Adam"** or **"Antoni"** voice profiles for a clean, documentary-style engineering readout.
