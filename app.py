"""
Omni-Mesh Local Backend Server
Flask + Flask-SocketIO implementation integrated with the SUMO/TraCI Gymnasium Environment
and the MockPerception layer (with Gaussian noise and thermal degradation modeling).
"""

import os
import sys
import time
import math
import random
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path
import numpy as np

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
from omnimesh.simulation.traci_env import SUMOTraCIEnvironment
from omnimesh.simulation.mock_perception import MockPerception
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
# SIMULATION CONTROLLER (SUMO + TRACI + GYMNASIUM + MOCK PERCEPTION)
# -----------------------------------------------------------------------------
class SUMOSimulationController:
    """
    Coordinates the true SUMO microscopic simulation through the Gymnasium-compliant
    SUMOTraCIEnvironment, filters ground truth via MockPerception, feeds Edge Agents,
    and streams real-time vehicle positions over WebSockets.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.is_running = False
        self.step_count = 0
        self.sim_time = 0.0
        self.step_duration = 0.5  # seconds per simulation tick

        # SUMO Gymnasium Environment & Perception
        self.env = SUMOTraCIEnvironment(gui=False, step_length=1.0)
        self.perception = MockPerception(mean_accuracy=0.98, std_accuracy=0.03)

        # Core Omni-Mesh components
        self.orchestrator = GlobalZoneOrchestrator(zone_id="zone_alpha", auto_approve_sim=True)
        self.consensus_filter = MultiNodeConsensusFilter(window_sec=30.0, required_nodes=2)
        self.serializer = MessageSerializer()
        self.zspf = ZSPFStateMachine(heartbeat_timeout=3.0, broker_timeout=5.0)

        # 16 Intersection Nodes mapped to SUMO TLS IDs (Row A-D, Col 0-3)
        self.intersections: Dict[str, Dict[str, Any]] = {}
        self._init_intersections()

        # Active Scenarios
        self.emergency_corridor: List[str] = []
        self.emergency_active = False
        self.containment_active = False
        self.containment_target = "SUSPECT-892"
        self.containment_node: str = "node_2_2"
        self.recent_events: List[Dict[str, Any]] = []

        # Latest step state cache
        self.latest_ground_truth_vehicles: Dict[str, Dict[str, Any]] = {}
        self.latest_detected_vehicles: Dict[str, Dict[str, Any]] = {}
        self.dropped_detections_count = 0

    def _init_intersections(self):
        # 16 internal intersections in grid_4x4.net.xml are A0..A3, B0..B3, C0..C3, D0..D3
        rows = ["A", "B", "C", "D"]
        for r_idx, r in enumerate(rows):
            for c in range(4):
                node_id = f"node_{r_idx}_{c}"
                tls_id = f"{r}{c}"
                # Real SUMO grid coordinates: A0=(80,80), D3=(530,530)
                x = 80.0 + c * 150.0
                y = 80.0 + r_idx * 150.0

                self.intersections[node_id] = {
                    "id": node_id,
                    "tls_id": tls_id,
                    "row": r_idx,
                    "col": c,
                    "x": x,
                    "y": y,
                    "phase": "EW" if (r_idx + c) % 2 == 0 else "NS",
                    "queue_ew": 0,
                    "queue_ns": 0,
                    "green_wave": False,
                    "barrier_lock": False,
                    "agent": EdgeNodeAgent(node_id, incoming_lanes=["north", "south", "east", "west"]),
                }

    def start_environment(self):
        """Initializes or restarts the SUMO TraCI process."""
        with self.lock:
            try:
                obs, info = self.env.reset()
                self.step_count = 0
                self.sim_time = 0.0
                self.latest_ground_truth_vehicles = info.get("ground_truth_vehicles", {})
                self.log_event("SUMO TraCI physics engine started successfully (Gymnasium Env active).", category="info")
            except Exception as e:
                self.log_event(f"Error starting SUMO: {e}", category="alert")

    def log_event(self, text: str, category: str = "info"):
        event = {
            "timestamp": time.strftime("%H:%M:%S"),
            "text": text,
            "category": category,
        }
        self.recent_events.insert(0, event)
        if len(self.recent_events) > 50:
            self.recent_events.pop()
        logger.info(f"[{category.upper()}] {text}")
        socketio.emit("event_logged", event)

    def trigger_emergency(self, corridor_row: int = 1):
        with self.lock:
            self.emergency_active = True
            self.emergency_corridor = [f"node_{corridor_row}_{c}" for c in range(4)]
            for nid in self.emergency_corridor:
                node = self.intersections[nid]
                node["green_wave"] = True
                node["phase"] = "EW"
                node["agent"].receive_emergency_request(self.emergency_corridor, target_phase=0)

            # Inject actual physical vehicle into SUMO via TraCI
            self.env.inject_emergency_vehicle("AMB_01", corridor_row=corridor_row)

        self.log_event(
            f"Ambulance AMB_01 injected into SUMO! P2P rolling Green Wave pre-cleared Row {corridor_row}: {self.emergency_corridor}",
            category="emergency",
        )

    def trigger_containment(self, target_plate: str = "SUSPECT-892"):
        with self.lock:
            self.containment_active = True
            self.containment_target = target_plate
            self.containment_node = "node_2_2"
            # Inject actual physical suspect vehicle into SUMO
            self.env.inject_suspect_vehicle(vehicle_id=target_plate, corridor_row=2)

        self.log_event(f"ANPR sighting for plate '{target_plate}' at node_2_0. Awaiting multi-node consensus...", category="containment")

        # Simulate 2-node consensus confirmation after 1 second
        def _confirm_consensus():
            time.sleep(1.2)
            consensus = self.consensus_filter.register_sighting(target_plate, "node_2_1", 0.96)
            if consensus:
                with self.lock:
                    target = self.intersections.get(self.containment_node)
                    if target:
                        target["barrier_lock"] = True
                        target["phase"] = "NS"
                    # Apply containment barrier in SUMO TraCI
                    self.env.set_containment_lockdown("C2")

                self.log_event(
                    f"Consensus confirmed ({len(consensus)} nodes). Tier-2 commands RED barrier at C2 ({self.containment_node})!",
                    category="containment",
                )

        threading.Thread(target=_confirm_consensus, daemon=True).start()

    def toggle_thermal_throttle(self, force_throttle: Optional[bool] = None):
        with self.lock:
            if force_throttle is not None:
                new_state = force_throttle
            else:
                new_state = not self.perception.thermal_throttle

            temp = 86.5 if new_state else 54.2
            self.perception.set_thermal_state(temp_c=temp, throttled=new_state)

        status_str = "ACTIVE (86.5°C CPU Spike - 40% Detection Dropout)" if new_state else "INACTIVE (54.2°C PWM Fan)"
        self.log_event(f"Hardware Thermal State: {status_str}", category="alert" if new_state else "info")

    def trigger_zspf_mode(self, mode: Optional[int] = None):
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
            self.emergency_active = False
            self.emergency_corridor = []
            self.containment_active = False
            self.zspf.current_mode = OperationalMode.MODE_0_FULL_MESH
            self.perception.set_thermal_state(temp_c=54.2, throttled=False)
            for node in self.intersections.values():
                node["green_wave"] = False
                node["barrier_lock"] = False
            self.start_environment()
        self.log_event("Scenario reset to nominal SUMO baseline traffic.", category="info")

    def step(self):
        """
        Executes one step of the SUMO physics loop via TraCI:
          1. Collects signal actions from edge agents.
          2. Advances SUMO physics via env.step(actions).
          3. Reads ground-truth vehicle coordinates from TraCI.
          4. Filters through MockPerception (Gaussian noise + thermal dropout).
          5. Updates edge agents' state exclusively through the perception pipeline.
        """
        with self.lock:
            if not self.env.is_connected:
                self.start_environment()

            self.step_count += 1
            self.sim_time = round(self.step_count * self.step_duration, 1)

            # Step 1: Collect actions from Tier-1 Edge Agents
            actions = []
            for node in self.intersections.values():
                if node["green_wave"]:
                    action = 0  # Green on arterial (EW)
                elif node["barrier_lock"]:
                    action = 1  # Red barrier on EW, green cross
                else:
                    action = node["agent"].step(current_time=self.sim_time)
                actions.append(action)
                node["phase"] = "EW" if action == 0 else "NS"

            # Step 2: Step the actual SUMO physics via Gymnasium TraCI environment
            actions_arr = np.array(actions, dtype=np.int32)
            obs, reward, terminated, truncated, info = self.env.step(actions_arr)

            # Step 3: Extract ground truth TraCI vehicle coordinates
            ground_truth = info.get("ground_truth_vehicles", {})
            self.latest_ground_truth_vehicles = ground_truth

            # Step 4: Process through MockPerception layer (Constraint 3 & 4)
            perception_result = self.perception.process_ground_truth(
                ground_truth_vehicles=ground_truth,
                intersections=self.intersections,
            )
            self.latest_detected_vehicles = perception_result["detected_vehicles"]
            self.dropped_detections_count = perception_result["dropped_count"]

            # Step 5: Update intersection queue displays from perception
            for nid, q_data in perception_result["node_queues"].items():
                if nid in self.intersections:
                    self.intersections[nid]["queue_ew"] = int(q_data.get("EW", 0))
                    self.intersections[nid]["queue_ns"] = int(q_data.get("NS", 0))

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            total_queue = sum(n["queue_ew"] + n["queue_ns"] for n in self.intersections.values())
            mode_int = int(self.zspf.current_mode)
            mode_names = ["Mode 0 (Full Mesh)", "Mode 1 (Autonomous P2P)", "Mode 2 (Island Max-Pressure)"]

            # Real ground-truth vehicles from TraCI with coordinates mapped for visual display
            vehicles_list = []
            # Normalize from SUMO bbox (0..610) to 0..1 scale for frontend
            for vid, vdata in self.latest_ground_truth_vehicles.items():
                gx, gy = vdata["position"]
                # Filtered status from MockPerception
                is_detected = vid in self.latest_detected_vehicles
                vehicles_list.append({
                    "id": vid,
                    "x": float(gx),
                    "y": float(gy),
                    "norm_x": float(np.clip(gx / 610.0, 0.0, 1.0)),
                    "norm_y": float(np.clip(1.0 - (gy / 610.0), 0.0, 1.0)),
                    "speed": float(vdata["speed"]),
                    "type": str(vdata["type"]),
                    "detected": is_detected,
                })

            telemetry = {
                "cpu_temp_c": round(self.perception.current_cpu_temp, 1),
                "yolo_fps": 4.5 if self.perception.thermal_throttle else 16.2,
                "rl_latency_ms": 1.15,
                "msg_size_bytes": 82,  # MessagePack
                "thermal_throttle": self.perception.thermal_throttle,
                "dropped_detections": self.dropped_detections_count,
                "fan_active": not self.perception.thermal_throttle,
            }

            nodes_data = [
                {
                    "id": n["id"],
                    "tls_id": n["tls_id"],
                    "row": n["row"],
                    "col": n["col"],
                    "x": n["x"],
                    "y": n["y"],
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
                "total_active_vehicles": len(self.latest_ground_truth_vehicles),
                "emergency_active": self.emergency_active,
                "containment_active": self.containment_active,
                "containment_target": self.containment_target,
                "vehicles": vehicles_list,
                "nodes": nodes_data,
                "telemetry": telemetry,
                "events": self.recent_events[:10],
            }

controller = SUMOSimulationController()

# -----------------------------------------------------------------------------
# BACKGROUND SIMULATION WORKER THREAD
# -----------------------------------------------------------------------------
def simulation_worker():
    """
    Background worker advancing the real SUMO TraCI physics engine
    and streaming real ground truth coordinates and telemetry over WebSockets.
    """
    logger.info("Background SUMO TraCI simulation worker thread started.")
    controller.start_environment()

    while True:
        if controller.is_running:
            try:
                controller.step()
                state = controller.get_state()
                socketio.emit("telemetry_update", state)
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                time.sleep(1.0)
        time.sleep(controller.step_duration)

# -----------------------------------------------------------------------------
# REST API ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({"status": "success", "data": controller.get_state()})

@app.route("/api/simulation/start", methods=["POST"])
def start_simulation():
    controller.is_running = True
    controller.log_event("SUMO physics simulation started / resumed.", category="info")
    socketio.emit("telemetry_update", controller.get_state())
    return jsonify({"status": "success", "is_running": True})

@app.route("/api/simulation/pause", methods=["POST"])
def pause_simulation():
    controller.is_running = False
    controller.log_event("SUMO physics simulation paused.", category="info")
    socketio.emit("telemetry_update", controller.get_state())
    return jsonify({"status": "success", "is_running": False})

@app.route("/api/simulation/step", methods=["POST"])
def step_simulation():
    controller.step()
    state = controller.get_state()
    socketio.emit("telemetry_update", state)
    return jsonify({"status": "success", "step": controller.step_count})

@app.route("/api/simulation/reset", methods=["POST"])
def reset_simulation():
    controller.reset_scenario()
    state = controller.get_state()
    socketio.emit("telemetry_update", state)
    return jsonify({"status": "success", "message": "Simulation reset"})

@app.route("/api/trigger/emergency", methods=["POST"])
def trigger_emergency():
    data = request.get_json(silent=True) or {}
    corridor_row = data.get("corridor_row", 1)
    controller.trigger_emergency(corridor_row=corridor_row)
    socketio.emit("telemetry_update", controller.get_state())
    return jsonify({"status": "success", "message": f"Green wave triggered along row {corridor_row}"})

@app.route("/api/trigger/containment", methods=["POST"])
def trigger_containment():
    data = request.get_json(silent=True) or {}
    target_plate = data.get("target_plate", "SUSPECT-892")
    controller.trigger_containment(target_plate=target_plate)
    socketio.emit("telemetry_update", controller.get_state())
    return jsonify({"status": "success", "message": f"Containment initiated for plate {target_plate}"})

@app.route("/api/trigger/zspf", methods=["POST"])
def trigger_zspf():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", None)
    controller.trigger_zspf_mode(mode=mode)
    socketio.emit("telemetry_update", controller.get_state())
    return jsonify({"status": "success", "mode": int(controller.zspf.current_mode)})

@app.route("/api/trigger/thermal", methods=["POST"])
def trigger_thermal():
    """Toggles simulated hardware thermal throttle (85°C CPU spike with 40% dropout)."""
    data = request.get_json(silent=True) or {}
    force_state = data.get("throttled", None)
    controller.toggle_thermal_throttle(force_throttle=force_state)
    socketio.emit("telemetry_update", controller.get_state())
    return jsonify({"status": "success", "throttled": controller.perception.thermal_throttle})

# -------------------------------------------------------------
# WEBSOCKET EVENT HANDLERS
# -------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    logger.info("WebSocket client connected to Omni-Mesh SUMO server.")
    emit("connected", {"message": "Connected to Omni-Mesh TraCI Backend", "state": controller.get_state()})

@socketio.on("disconnect")
def handle_disconnect():
    logger.info("WebSocket client disconnected.")

@socketio.on("client_command")
def handle_client_command(data):
    action = data.get("action")
    if action == "start":
        controller.is_running = True
    elif action == "pause":
        controller.is_running = False
    elif action == "step":
        controller.step()
    elif action == "emergency":
        controller.trigger_emergency()
    elif action == "containment":
        controller.trigger_containment()
    elif action == "zspf":
        controller.trigger_zspf_mode()
    elif action == "thermal":
        controller.toggle_thermal_throttle()
    elif action == "reset":
        controller.reset_scenario()

    emit("telemetry_update", controller.get_state(), broadcast=True)

# -------------------------------------------------------------
# SERVER ENTRY POINT
# -------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting Omni-Mesh SUMO TraCI Local Backend Server on http://localhost:5000 ...")
    threading.Thread(target=simulation_worker, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
