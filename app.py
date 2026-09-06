"""
Omni-Mesh Local Backend Server
Flask + Flask-SocketIO implementation for simulation telemetry, REST control endpoints,
and decoupled background co-simulation loop (pure software / no hardware required).
"""

import os
import sys
import time
import math
import random
import threading
from typing import Dict, Any, List
from pathlib import Path

# Insert project root for module discovery
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from flask import Flask, jsonify, request, send_from_directory
    from flask_socketio import SocketIO, emit
except ImportError:
    print(
        "Missing required dependencies for local backend server.\n"
        "Please run:\n"
        "    pip install flask flask-socketio simple-websocket\n"
        "or install from requirements.txt."
    )
    sys.exit(1)

from omnimesh.utils.logger import logger
from omnimesh.tier1_edge.agent import EdgeNodeAgent
from omnimesh.tier1_edge.zspf_state_machine import ZSPFStateMachine, OperationalMode
from omnimesh.tier2_orchestrator.orchestrator import GlobalZoneOrchestrator
from omnimesh.vision.consensus import MultiNodeConsensusFilter
from omnimesh.comms.serializer import MessageSerializer

# -----------------------------------------------------------------------------
# FLASK & SOCKET-IO CONFIGURATION
# -----------------------------------------------------------------------------
app = Flask(__name__, static_folder=".")
app.config["SECRET_KEY"] = "omnimesh-secret-key-2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# -----------------------------------------------------------------------------
# SIMULATION STATE & PURE-SOFTWARE HARNESS (NO HARDWARE)
# -----------------------------------------------------------------------------
GRID_ROWS = 4
GRID_COLS = 4

class SimulationHarness:
    """
    Pure software co-simulation controller managing in-memory intersection nodes,
    vehicle flows, emergency green waves, ANPR containment, and simulated telemetry.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.is_running = False
        self.step_count = 0
        self.sim_time = 0.0
        self.step_duration = 0.5  # seconds per simulation tick
        
        # Core Omni-Mesh components
        self.orchestrator = GlobalZoneOrchestrator(zone_id="zone_alpha", auto_approve_sim=True)
        self.consensus_filter = MultiNodeConsensusFilter(window_sec=30.0, required_nodes=2)
        self.serializer = MessageSerializer()
        self.zspf = ZSPFStateMachine(heartbeat_timeout=3.0, broker_timeout=5.0)

        # 4x4 Grid Intersection Agents
        self.intersections: Dict[str, Dict[str, Any]] = {}
        self._init_intersections()

        # Active Scenarios
        self.emergency_corridor: List[str] = []
        self.emergency_active = False
        self.containment_active = False
        self.containment_target = "SUSPECT-892"
        self.containment_node: str = "node_2_2"
        self.recent_events: List[Dict[str, Any]] = []

    def _init_intersections(self):
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                node_id = f"node_{r}_{c}"
                self.intersections[node_id] = {
                    "id": node_id,
                    "row": r,
                    "col": c,
                    "phase": "EW" if (r + c) % 2 == 0 else "NS",
                    "queue_ew": random.randint(2, 8),
                    "queue_ns": random.randint(2, 8),
                    "timer": random.randint(15, 30),
                    "green_wave": False,
                    "barrier_lock": False,
                    "agent": EdgeNodeAgent(node_id, incoming_lanes=["north", "south", "east", "west"]),
                }

    def log_event(self, text: str, category: str = "info"):
        event = {
            "timestamp": time.strftime("%H:%M:%S"),
            "text": text,
            "category": category,
        }
        with self.lock:
            self.recent_events.insert(0, event)
            if len(self.recent_events) > 50:
                self.recent_events.pop()
        logger.info(f"[{category.upper()}] {text}")
        socketio.emit("event_logged", event)

    def trigger_emergency(self, corridor_row: int = 1):
        with self.lock:
            self.emergency_active = True
            self.emergency_corridor = [f"node_{corridor_row}_{c}" for c in range(GRID_COLS)]
            for nid in self.emergency_corridor:
                node = self.intersections[nid]
                node["green_wave"] = True
                node["phase"] = "EW"
                node["agent"].receive_emergency_request(self.emergency_corridor, target_phase=0)
        self.log_event(
            f"Ambulance detected! P2P rolling Green Wave pre-cleared Row {corridor_row} nodes: {self.emergency_corridor}",
            category="emergency",
        )

    def trigger_containment(self, target_plate: str = "SUSPECT-892"):
        with self.lock:
            self.containment_active = True
            self.containment_target = target_plate
            self.containment_node = "node_2_2"
        self.log_event(f"ANPR sighting for plate '{target_plate}' at node_2_0 (Conf: 0.95). Awaiting consensus...", category="containment")

        # Simulate 2-node consensus confirmation after 1 second
        def _confirm_consensus():
            time.sleep(1.0)
            consensus = self.consensus_filter.register_sighting(target_plate, "node_2_1", 0.96)
            if consensus:
                with self.lock:
                    target = self.intersections.get(self.containment_node)
                    if target:
                        target["barrier_lock"] = True
                        target["phase"] = "NS"  # Lock East-West flow
                self.log_event(
                    f"Consensus verified ({len(consensus)} nodes). Tier-2 commands RED containment barrier at {self.containment_node}!",
                    category="containment",
                )

        threading.Thread(target=_confirm_consensus, daemon=True).start()

    def trigger_zspf_mode(self, mode: int = None):
        with self.lock:
            if mode is None:
                current = int(self.zspf.current_mode)
                next_mode = OperationalMode((current + 1) % 3)
            else:
                next_mode = OperationalMode(mode % 3)
            self.zspf.current_mode = next_mode
            mode_name = next_mode.name
        self.log_event(f"ZSPF state machine transitioned to {mode_name}", category="zspf")

    def reset_scenario(self):
        with self.lock:
            self.step_count = 0
            self.emergency_active = False
            self.emergency_corridor = []
            self.containment_active = False
            self.zspf.current_mode = OperationalMode.MODE_0_FULL_MESH
            for node in self.intersections.values():
                node["green_wave"] = False
                node["barrier_lock"] = False
                node["queue_ew"] = random.randint(2, 8)
                node["queue_ns"] = random.randint(2, 8)
                node["phase"] = "EW" if (node["row"] + node["col"]) % 2 == 0 else "NS"
        self.log_event("Simulation scenario reset to nominal baseline traffic.", category="info")

    def step(self):
        with self.lock:
            self.step_count += 1
            self.sim_time += self.step_duration

            # Update traffic dynamics across nodes
            for node in self.intersections.values():
                if not node["green_wave"] and not node["barrier_lock"]:
                    node["timer"] -= 1
                    if node["timer"] <= 0:
                        node["phase"] = "NS" if node["phase"] == "EW" else "EW"
                        node["timer"] = random.randint(15, 30)

                # Queue dynamics
                if node["phase"] == "EW":
                    node["queue_ew"] = max(0, node["queue_ew"] - random.randint(1, 2))
                    node["queue_ns"] = min(25, node["queue_ns"] + random.randint(0, 1))
                else:
                    node["queue_ns"] = max(0, node["queue_ns"] - random.randint(1, 2))
                    node["queue_ew"] = min(25, node["queue_ew"] + random.randint(0, 1))

                # Step individual agent policy
                node["agent"].step(current_time=self.sim_time)

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            total_queue = sum(n["queue_ew"] + n["queue_ns"] for n in self.intersections.values())
            mode_int = int(self.zspf.current_mode)
            mode_names = ["Mode 0 (Full Mesh)", "Mode 1 (Autonomous P2P)", "Mode 2 (Island Max-Pressure)"]

            # Pure software simulated hardware telemetry (modeling Raspberry Pi 4B)
            temp_c = 54.0 + 2.0 * math.sin(self.step_count * 0.1)
            fps = 16.2 + 0.8 * math.cos(self.step_count * 0.08)

            telemetry = {
                "cpu_temp_c": round(temp_c, 1),
                "yolo_fps": round(fps, 1),
                "rl_latency_ms": 1.15,
                "msg_size_bytes": 82,  # MessagePack
                "thermal_throttle": False,
                "fan_active": True,
            }

            nodes_data = [
                {
                    "id": n["id"],
                    "row": n["row"],
                    "col": n["col"],
                    "phase": n["phase"],
                    "queue_ew": n["queue_ew"],
                    "queue_ns": n["queue_ns"],
                    "green_wave": n["green_wave"],
                    "barrier_lock": n["barrier_lock"],
                }
                for n in self.intersections.values()
            ]

            return {
                "is_running": self.is_running,
                "step_count": self.step_count,
                "sim_time": round(self.sim_time, 1),
                "zspf_mode": mode_int,
                "zspf_mode_label": mode_names[mode_int],
                "total_vehicles_queued": total_queue,
                "emergency_active": self.emergency_active,
                "containment_active": self.containment_active,
                "containment_target": self.containment_target,
                "nodes": nodes_data,
                "telemetry": telemetry,
                "events": self.recent_events[:10],
            }

harness = SimulationHarness()

# -----------------------------------------------------------------------------
# BACKGROUND SIMULATION WORKER THREAD
# -----------------------------------------------------------------------------
def simulation_worker():
    """
    Background worker loop advancing the simulation and streaming telemetry via WebSockets.
    """
    logger.info("Background simulation worker thread started.")
    while True:
        if harness.is_running:
            harness.step()
            state = harness.get_state()
            socketio.emit("telemetry_update", state)
        time.sleep(harness.step_duration)

# -----------------------------------------------------------------------------
# REST API ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """Serves the interactive web dashboard."""
    return send_from_directory(".", "index.html")

@app.route("/api/status", methods=["GET"])
def get_status():
    """Returns the current simulation state and telemetry."""
    return jsonify({"status": "success", "data": harness.get_state()})

@app.route("/api/simulation/start", methods=["POST"])
def start_simulation():
    """Starts / resumes the simulation loop."""
    harness.is_running = True
    harness.log_event("Simulation loop started / resumed.", category="info")
    socketio.emit("telemetry_update", harness.get_state())
    return jsonify({"status": "success", "is_running": True})

@app.route("/api/simulation/pause", methods=["POST"])
def pause_simulation():
    """Pauses the simulation loop."""
    harness.is_running = False
    harness.log_event("Simulation loop paused.", category="info")
    socketio.emit("telemetry_update", harness.get_state())
    return jsonify({"status": "success", "is_running": False})

@app.route("/api/simulation/step", methods=["POST"])
def step_simulation():
    """Executes a single simulation step."""
    harness.step()
    state = harness.get_state()
    socketio.emit("telemetry_update", state)
    return jsonify({"status": "success", "step": harness.step_count})

@app.route("/api/simulation/reset", methods=["POST"])
def reset_simulation():
    """Resets the simulation grid and scenarios."""
    harness.reset_scenario()
    state = harness.get_state()
    socketio.emit("telemetry_update", state)
    return jsonify({"status": "success", "message": "Simulation reset"})

@app.route("/api/trigger/emergency", methods=["POST"])
def trigger_emergency():
    """Manually triggers an emergency vehicle P2P Green Wave."""
    data = request.get_json(silent=True) or {}
    corridor_row = data.get("corridor_row", 1)
    harness.trigger_emergency(corridor_row=corridor_row)
    socketio.emit("telemetry_update", harness.get_state())
    return jsonify({"status": "success", "message": f"Green wave triggered along row {corridor_row}"})

@app.route("/api/trigger/containment", methods=["POST"])
def trigger_containment():
    """Manually triggers an ANPR threat watchlist containment event."""
    data = request.get_json(silent=True) or {}
    target_plate = data.get("target_plate", "SUSPECT-892")
    harness.trigger_containment(target_plate=target_plate)
    socketio.emit("telemetry_update", harness.get_state())
    return jsonify({"status": "success", "message": f"Containment initiated for plate {target_plate}"})

@app.route("/api/trigger/zspf", methods=["POST"])
def trigger_zspf():
    """Toggles or sets the active ZSPF operational mode."""
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", None)
    harness.trigger_zspf_mode(mode=mode)
    socketio.emit("telemetry_update", harness.get_state())
    return jsonify({"status": "success", "mode": int(harness.zspf.current_mode)})

# -------------------------------------------------------------
# WEBSOCKET EVENT HANDLERS
# -------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    logger.info("WebSocket client connected to Omni-Mesh server.")
    emit("connected", {"message": "Connected to Omni-Mesh Local Backend Server", "state": harness.get_state()})

@socketio.on("disconnect")
def handle_disconnect():
    logger.info("WebSocket client disconnected.")

@socketio.on("client_command")
def handle_client_command(data):
    """
    Handles commands sent directly via WebSocket:
    {'action': 'start' | 'pause' | 'step' | 'emergency' | 'containment' | 'zspf'}
    """
    action = data.get("action")
    if action == "start":
        harness.is_running = True
    elif action == "pause":
        harness.is_running = False
    elif action == "step":
        harness.step()
    elif action == "emergency":
        harness.trigger_emergency()
    elif action == "containment":
        harness.trigger_containment()
    elif action == "zspf":
        harness.trigger_zspf_mode()
    elif action == "reset":
        harness.reset_scenario()

    emit("telemetry_update", harness.get_state(), broadcast=True)

# -------------------------------------------------------------
# SERVER ENTRY POINT
# -------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting Omni-Mesh Local Backend Server on http://localhost:5000 ...")
    # Start the background co-simulation loop
    threading.Thread(target=simulation_worker, daemon=True).start()
    # Launch Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
