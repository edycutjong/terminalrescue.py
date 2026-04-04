#!/usr/bin/env python3
import time
import json
import uuid
import sys
import os
import subprocess
import threading
import tty
import termios
from collections import deque
import paho.mqtt.client as mqtt

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich import box

import config

# ──────────────────────────────────────────────────────────────────
#  Palette
# ──────────────────────────────────────────────────────────────────
DRONE_PALETTE = {
    "drone_1": {"color": "#00d4ff", "icon": "◆", "label": "ALPHA"},
    "drone_2": {"color": "#ff6ec7", "icon": "◆", "label": "BRAVO"},
    "drone_3": {"color": "#ffe066", "icon": "◆", "label": "CHARLIE"},
    "drone_4": {"color": "#66ff99", "icon": "◆", "label": "DELTA"},
    "drone_5": {"color": "#b388ff", "icon": "◆", "label": "ECHO"},
}

STATUS_STYLES = {
    "READY":      ("bold green",  "● READY"),
    "CLAIMING":   ("bold yellow", "▸ CLAIMING"),
    "SEARCHING":  ("bold cyan",   "◎ SEARCHING"),
    "COMPLETE":   ("bold green",  "✓ COMPLETE"),
    "CONNECTING": ("dim",         "… CONNECTING"),
    "OFFLINE":    ("bold red",    "✕ OFFLINE"),
}

EVENT_COLORS = {
    "HELLO":     "green",
    "CLAIM":     "cyan",
    "RELEASE":   "red",
    "HEARTBEAT": "dim",
    "SEARCH":    "#66ff99",
    "SPAWN":     "green",
    "KILL":      "bold red",
    "SYSTEM":    "bold green",
}

def speak(text):
    if sys.platform == "darwin":
        # Run asynchronously to avoid blocking the rich UI refresh
        subprocess.Popen(["say", "-v", "Samantha", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



class ObserverNode:
    def __init__(self):
        self.node_id = "observer"
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{self.node_id}_{uuid.uuid4().hex[:6]}",
            protocol=mqtt.MQTTv5,
        )
        self.client.username_pw_set(self.node_id, "demopass")

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # ── State ────────────────────────────────────────────────
        self.drone_status = {}
        self.all_claims = {}
        self.searched_sectors = set()
        self.event_log = deque(maxlen=18)  # rolling log
        self.start_time = None # Timer starts after setup
        self.total_messages = 0
        self.claim_count = 0
        self.release_count = 0
        self.mission_complete_announced = False


        # ── Drone subprocess management ──────────────────────────
        self.drone_procs = []  # list of (drone_id, Popen)
        self.kill_requested = False
        self.quit_requested = False

    # ── MQTT Callbacks ───────────────────────────────────────────
    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.client.subscribe("swarm/#", qos=1)
            self._log_event("SYSTEM", "Observer connected to FoxMQ mesh", "green")

    def on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            msg_type = payload.get("type")
            sender = payload.get("drone_id", payload.get("releasing_drone", "unknown"))
            self.total_messages += 1

            if msg_type == "HELLO":
                label = DRONE_PALETTE.get(sender, {}).get("label", sender)
                self._log_event("HELLO", f"{label} ({sender}) joined the mesh", EVENT_COLORS["HELLO"])
                self.drone_status.setdefault(sender, {})
                self.drone_status[sender]["last_seen"] = time.time()
                self.drone_status[sender]["status"] = payload.get("status", "READY")

            elif msg_type == "HEARTBEAT":
                self.drone_status.setdefault(sender, {})
                # If we've already officially marked this drone as OFFLINE, strictly 
                # ignore any significantly delayed ghost heartbeat messages 
                # that arrive late in the network buffer.
                if "OFFLINE" in self.drone_status[sender].get("status", ""):
                    return

                self.drone_status[sender]["last_seen"] = time.time()
                self.drone_status[sender]["status"] = payload.get("status", "UNKNOWN")
                self.drone_status[sender]["pos"] = payload.get("position")
                self.drone_status[sender]["claimed"] = payload.get("sectors_claimed", [])
                prev_searched = set(self.drone_status[sender].get("searched", []))
                new_searched = payload.get("sectors_searched", [])
                self.drone_status[sender]["searched"] = new_searched
                for sector in new_searched:
                    if sector not in self.searched_sectors:
                        self.searched_sectors.add(sector)
                        label = DRONE_PALETTE.get(sender, {}).get("label", sender)
                        color = DRONE_PALETTE.get(sender, {}).get("color", "white")
                        self._log_event("SEARCH", f"[{color}]{label}[/{color}] searched sector {sector}", EVENT_COLORS["SEARCH"])

            elif msg_type == "CLAIM":
                sector = payload.get("sector")
                if sector and sector not in self.all_claims:
                    self.all_claims[sector] = sender
                    self.claim_count += 1
                    
                    if self.start_time is None and len(self.all_claims) >= config.TOTAL_SECTORS:
                        self.start_time = time.time()
                        self._log_event("SYSTEM", "Setup sequence complete. Initiating Search Timer...", "green")
                        speak("Swarm bootup complete. Initial grid locked. Commencing decentralized search.")

                    label = DRONE_PALETTE.get(sender, {}).get("label", sender)
                    self._log_event("CLAIM", f"{label} claimed sector {sector}", EVENT_COLORS["CLAIM"])

            elif msg_type == "RELEASE":
                dead_drone = payload.get("dead_drone")
                released = payload.get("sectors_released", [])
                self.release_count += 1
                if dead_drone in self.drone_status:
                    self.drone_status[dead_drone]["status"] = "OFFLINE"
                for s in list(self.all_claims.keys()):
                    if self.all_claims.get(s) == dead_drone:
                        del self.all_claims[s]
                label = DRONE_PALETTE.get(dead_drone, {}).get("label", dead_drone)
                self._log_event(
                    "RELEASE",
                    f"☠ {label} OFFLINE — {len(released)} sector(s) freed",
                    EVENT_COLORS["RELEASE"],
                )
                speak(f"Mesh fault detected. Drone {label} heartbeat lost. Releasing orphaned sectors.")

        except Exception:
            pass

    def _log_event(self, event_type: str, text: str, color: str):
        ts = time.strftime("%H:%M:%S")
        self.event_log.append(f"[dim]{ts}[/dim] [{color}][{event_type}][/{color}] {text}")

    # ── Renderers ────────────────────────────────────────────────

    def _build_title(self) -> str:
        if self.start_time is None:
            mins, secs = 0, 0
        else:
            elapsed = time.time() - self.start_time
            mins, secs = divmod(int(elapsed), 60)
        active = sum(
            1 for d in self.drone_status.values()
            if d.get("status") and "OFFLINE" not in d["status"]
        )
        total = len(self.drone_status)
        searched = len(self.searched_sectors)
        pct = int(searched / config.TOTAL_SECTORS * 100) if config.TOTAL_SECTORS else 0
        return (
            f"[bold #ff6ec7]◈ TERMINAL[/bold #ff6ec7][bold #00d4ff]RESCUE[/bold #00d4ff]"
            f"[bold #ff6ec7] ◈[/bold #ff6ec7]"
            f"  [bold white]⏱ {mins:02d}:{secs:02d}[/bold white]"
            f"  [bold green]⬡ {active}[/bold green][white]/{total}[/white]"
            f"  [bold cyan]▣ {searched}[/bold cyan][white]/{config.TOTAL_SECTORS}[/white]"
            f"  [bold #ffe066]◉ {pct}%[/bold #ffe066]"
            f"  [bold white]✉ {self.total_messages}[/bold white]"
        )

    def _render_grid(self) -> Panel:
        table = Table(
            box=None,
            show_header=False,
            show_edge=False,
            pad_edge=True,
            padding=(0, 1),
        )

        # Add columns
        for _ in range(config.GRID_SIZE_X):
            table.add_column(justify="center", width=3)

        for y in range(config.GRID_SIZE_Y):
            row_cells = []
            for x in range(config.GRID_SIZE_X):
                sector = f"{x}_{y}"
                cell = "[dim]·[/dim]"

                if sector in self.searched_sectors:
                    cell = "[bold green]✓[/bold green]"
                elif sector in self.all_claims:
                    owner = self.all_claims[sector]
                    pal = DRONE_PALETTE.get(owner, {"color": "white"})
                    status = self.drone_status.get(owner, {}).get("status", "")
                    if "OFFLINE" in status:
                        cell = "[bold red]✕[/bold red]"
                    else:
                        cell = f"[{pal['color']}]■[/{pal['color']}]"

                # Overlay drone positions (highest priority)
                for d_id, d_info in self.drone_status.items():
                    if "OFFLINE" in d_info.get("status", ""):
                        continue
                    pos = d_info.get("pos", {})
                    if pos and pos.get("x") == x and pos.get("y") == y:
                        pal = DRONE_PALETTE.get(d_id, {"color": "white"})
                        cell = f"[bold {pal['color']}]@[/bold {pal['color']}]"

                row_cells.append(cell)
            table.add_row(*row_cells)

        # Legend
        legend_parts = []
        legend_parts.append("[dim]·[/dim] [white]Free[/white]")
        for d_id, pal in DRONE_PALETTE.items():
            if d_id in self.drone_status:
                legend_parts.append(f"[{pal['color']}]■ {pal['label']}[/{pal['color']}]")
        legend_parts.append("[bold green]✓ Done[/bold green]")
        legend_parts.append("[bold red]✕ Dead[/bold red]")
        legend_parts.append("[bold white]@ Drone[/bold white]")
        from rich.console import Group

        # Group table and legend so it wraps safely inside the panel
        legend_display = Align.center(Text.from_markup("  ".join(legend_parts), justify="center"))
        
        display_group = Group(
            Align.center(table),
            Text(""), # spacing
            legend_display
        )

        return Panel(
            display_group,
            title=self._build_title(),
            border_style="#333333",
            box=box.DOUBLE,
            padding=(1, 2),
        )

    def _render_telemetry(self) -> Panel:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            border_style="#333333",
            header_style="bold dim",
            expand=True,
        )
        table.add_column("DRONE", justify="left", style="bold", min_width=10)
        table.add_column("STATUS", justify="center", min_width=14)
        table.add_column("SECTORS", justify="center", min_width=8)
        table.add_column("SEARCHED", justify="center", min_width=8)
        table.add_column("LAST SEEN", justify="right", min_width=8)

        now = time.time()
        for d_id in sorted(self.drone_status.keys()):
            d_info = self.drone_status[d_id]
            pal = DRONE_PALETTE.get(d_id, {"color": "white", "label": d_id})

            # Drone name
            name = f"[{pal['color']}]{pal['label']}[/{pal['color']}]"

            # Status badge — prefer heartbeat data, but infer from observer state
            status_raw = d_info.get("status", "UNKNOWN")
            if "OFFLINE" in status_raw:
                status_key = "OFFLINE"
            else:
                status_key = status_raw
            style, badge = STATUS_STYLES.get(status_key, ("dim", f"? {status_key}"))
            status_cell = f"[{style}]{badge}[/{style}]"

            # Sector counts — derived from observer's real-time tracking (not stale heartbeat)
            claimed = sum(1 for owner in self.all_claims.values() if owner == d_id)
            searched_hb = d_info.get("searched", [])
            searched = len(searched_hb)

            # Last seen
            age = now - d_info.get("last_seen", now)
            if age < 5:
                age_str = f"[green]{age:.0f}s[/green]"
            elif age < 15:
                age_str = f"[yellow]{age:.0f}s[/yellow]"
            else:
                age_str = f"[red]{age:.0f}s[/red]"

            table.add_row(name, status_cell, str(claimed), str(searched), age_str)

        return Panel(
            table,
            title="[bold #ff6ec7]⬡ DRONE TELEMETRY[/bold #ff6ec7]",
            border_style="#333333",
            box=box.DOUBLE,
            padding=(0, 1),
        )

    def _render_event_log(self) -> Panel:
        if not self.event_log:
            content = Text("Waiting for mesh activity…", style="dim italic")
        else:
            lines = list(reversed(self.event_log))
            content = Text.from_markup("\n".join(lines))

        return Panel(
            content,
            title="[bold #ffe066]✉ BFT EVENT LOG[/bold #ffe066]",
            border_style="#333333",
            box=box.DOUBLE,
            padding=(0, 1),
        )

    def _render_progress(self) -> Panel:
        searched = len(self.searched_sectors)
        total = config.TOTAL_SECTORS
        pct = searched / total if total else 0

        bar_width = 40
        filled = int(pct * bar_width)
        empty = bar_width - filled

        active = sum(
            1 for d in self.drone_status.values()
            if d.get("status") and "OFFLINE" not in d["status"]
        )

        # Bar color — green glow at 100%
        bar_color = "bold #66ff99" if pct >= 1.0 else "bold #00d4ff"

        content = Text()
        content.append(" ")
        content.append("█" * filled, style=bar_color)
        content.append("░" * empty, style="#333333")
        if pct >= 1.0:
            content.append(f"  🎉 {searched}/{total} ({int(pct * 100)}%)", style="bold #66ff99")
        else:
            content.append(f"  {searched}/{total} ({int(pct * 100)}%)", style="bold white")
        content.append(f"   Claims: ", style="white")
        content.append(f"{self.claim_count}", style="bold cyan")
        content.append(f"  Releases: ", style="white")
        content.append(f"{self.release_count}", style="bold red")
        content.append(f"  Active: ", style="white")
        content.append(f"{active}", style="bold green")

        if pct >= 1.0 and not getattr(self, "mission_complete_announced", False):
            self.mission_complete_announced = True
            speak("Mesh completely stabilized. All sectors successfully rescued. Mission complete.")

        progress_title = (
            "[bold #66ff99]🎉 MISSION COMPLETE[/bold #66ff99]"
            if pct >= 1.0
            else "[bold #66ff99]◉ MISSION PROGRESS[/bold #66ff99]"
        )

        return Panel(
            content,
            title=progress_title,
            subtitle="[white]Press[/white] [bold yellow]K[/bold yellow] [white]kill drone[/white]  [bold yellow]Q[/bold yellow] [white]quit[/white]",
            subtitle_align="right",
            border_style="#66ff99" if pct >= 1.0 else "#333333",
            box=box.DOUBLE,
            padding=(0, 0),
        )

    # ── Drone process management ──────────────────────────────────

    def _spawn_drones(self, count=5):
        """Launch drone subprocesses with staggered starts."""
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drone.py")
        for i in range(1, count + 1):
            drone_id = f"drone_{i}"
            proc = subprocess.Popen(
                [sys.executable, script, "--id", drone_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.drone_procs.append((drone_id, proc))
            label = DRONE_PALETTE.get(drone_id, {}).get("label", drone_id)
            self._log_event("SPAWN", f"Launched {label} (PID {proc.pid})", "green")
            if i < count:
                time.sleep(0.3)  # Fast spawn so all drones join mesh quickly

    def _kill_next_drone(self):
        """Kill the first alive drone — returns its label or None."""
        for i, (drone_id, proc) in enumerate(self.drone_procs):
            if proc.poll() is None:  # still alive
                proc.terminate()
                label = DRONE_PALETTE.get(drone_id, {}).get("label", drone_id)
                self._log_event("KILL", f"☠ Terminated {label} (PID {proc.pid})", "red")
                speak(f"Critical warning. Kill switch engaged. Drone {label} manually terminated.")
                return label
        return None

    def _cleanup_drones(self):
        """Terminate all drone subprocesses."""
        for drone_id, proc in self.drone_procs:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in self.drone_procs:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    def _key_listener(self):
        """Background thread: read single keystrokes."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not self.quit_requested:
                ch = sys.stdin.read(1)
                if ch in ('k', 'K'):
                    self.kill_requested = True
                elif ch in ('q', 'Q'):
                    self.quit_requested = True
                    break
        except Exception:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # ── Main Loop ────────────────────────────────────────────────

    def run(self):
        # Retry connection — FoxMQ may not be up yet
        from rich.console import Console
        console = Console()
        connected = False
        while not connected:
            try:
                self.client.connect(config.FOXMQ_HOST, config.FOXMQ_PORT, 60)
                connected = True
            except (ConnectionRefusedError, OSError) as e:
                console.print(
                    f"[yellow]⏳ Waiting for FoxMQ broker at "
                    f"{config.FOXMQ_HOST}:{config.FOXMQ_PORT}… ({e})[/yellow]"
                )
                time.sleep(2)

        self.client.loop_start()
        self._log_event("SYSTEM", "Connected to FoxMQ broker", "green")
        speak("Mission control online. Connected to Fox MQ proxy.")

        # Start keyboard listener thread
        key_thread = threading.Thread(target=self._key_listener, daemon=True)
        key_thread.start()

        # Build layout tree
        layout = Layout()
        layout.split_column(
            Layout(name="body"),
            Layout(name="progress", size=3),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2),
        )
        layout["right"].split_column(
            Layout(name="telemetry", ratio=1),
            Layout(name="events", ratio=1),
        )

        try:
            with Live(layout, refresh_per_second=4, screen=True):
                # Spawn drones in background AFTER display is live
                spawn_thread = threading.Thread(
                    target=self._spawn_drones, kwargs={"count": 5}, daemon=True
                )
                spawn_thread.start()

                while not self.quit_requested:
                    # Handle kill request
                    if self.kill_requested:
                        self.kill_requested = False
                        self._kill_next_drone()

                    now = time.time()
                    for d_id, d_info in list(self.drone_status.items()):
                        if "OFFLINE" not in d_info.get("status", ""):
                            if now - d_info.get("last_seen", now) > 3.0:
                                d_info["status"] = "OFFLINE"
                                for s in list(self.all_claims.keys()):
                                    if self.all_claims.get(s) == d_id:
                                        del self.all_claims[s]

                    layout["left"].update(self._render_grid())
                    layout["telemetry"].update(self._render_telemetry())
                    layout["events"].update(self._render_event_log())
                    layout["progress"].update(self._render_progress())
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup_drones()
            self.client.disconnect()


if __name__ == "__main__":
    obs = ObserverNode()
    obs.run()
