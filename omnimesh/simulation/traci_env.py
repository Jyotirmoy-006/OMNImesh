"""
Omni-Mesh TraCI Gymnasium Simulation Environment
Inherits strictly from gymnasium.Env, controls SUMO microscopic physics via TraCI,
and pipes real ground-truth vehicle coordinates to perception and backend layers.
"""

import os
import sys
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    import gym
    from gym import spaces

try:
    import traci
    import sumolib
    HAS_TRACI = True
except ImportError:
    HAS_TRACI = False

from omnimesh.utils.logger import logger
from omnimesh.tier1_edge.reward_shaping import DualObjectiveRewardShaper

DEFAULT_SUMOCFG = str(Path(__file__).resolve().parent.parent.parent / "data" / "networks" / "grid_4x4.sumocfg")
DEFAULT_NETFILE = str(Path(__file__).resolve().parent.parent.parent / "data" / "networks" / "grid_4x4.net.xml")

# Candidate SUMO paths
SUMO_SEARCH_PATHS = [
    r"C:\Users\Asus\sumo-bin\sumo-1.27.1\bin\sumo.exe",
    os.path.join(os.environ.get("SUMO_HOME", ""), "bin", "sumo.exe") if os.environ.get("SUMO_HOME") else "",
]

class SUMOTraCIEnvironment(gym.Env):
    """
    Gymnasium-compliant environment controlling SUMO through TraCI.
    Spawns the simulation, controls traffic light phases, extracts microscopic
    vehicle ground truth positions, and handles scenario event injections.
    Observation space is augmented with the binary threat flag m(t) and P2P neighbor messages.
    """
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 2}

    def __init__(
        self,
        sumocfg_path: str = DEFAULT_SUMOCFG,
        net_file: str = DEFAULT_NETFILE,
        gui: bool = False,
        step_length: float = 1.0,
        max_steps: int = 3600,
        render_mode: Optional[str] = None,
    ):
        super().__init__()
        self.sumocfg_path = str(sumocfg_path)
        self.net_file = str(net_file)
        self.gui = gui
        self.step_length = step_length
        self.max_steps = max_steps
        self.render_mode = render_mode

        self.current_step = 0
        self.is_connected = False
        self.traci_label = f"omnimesh_traci_{os.getpid()}"
        self.conn = None

        # Threat flag m(t) in {0, 1} injected by Tier-2 Orchestrator
        self.threat_mode: int = 0
        self.containment_target_plate: str = "SUSPECT-892"
        self.containment_trap_node: str = "C2"  # (row 2, col 2)
        self.reward_shaper = DualObjectiveRewardShaper()

        # 16 Core Intersection TLS IDs (Row A-D, Col 0-3)
        self.grid_rows = ["A", "B", "C", "D"]
        self.tls_ids: List[str] = [
            f"{row}{col}" for row in self.grid_rows for col in range(4)
        ]

        # Action space: 4 signal phases for each of the 16 intersections
        self.action_space = spaces.MultiDiscrete([4] * len(self.tls_ids))

        # Observation space per node (7 features):
        # [q_approach_0, q_approach_1, neighbor_q_N, neighbor_q_S, neighbor_q_E, neighbor_q_W, m_threat]
        # Total observation vector dimension: 16 * 7 = 112
        self.features_per_node = 7
        self.total_obs_dim = len(self.tls_ids) * self.features_per_node
        self.observation_space = spaces.Box(
            low=0.0,
            high=100.0,
            shape=(self.total_obs_dim,),
            dtype=np.float32,
        )

        self._resolve_sumo_binary()

    def _resolve_sumo_binary(self) -> str:
        binary_name = "sumo-gui" if self.gui else "sumo"
        for candidate in SUMO_SEARCH_PATHS:
            if candidate and os.path.isfile(candidate):
                if self.gui and "sumo.exe" in candidate:
                    gui_candidate = candidate.replace("sumo.exe", "sumo-gui.exe")
                    if os.path.isfile(gui_candidate):
                        self.sumo_binary = gui_candidate
                        return self.sumo_binary
                self.sumo_binary = candidate
                return self.sumo_binary

        if HAS_TRACI:
            try:
                self.sumo_binary = sumolib.checkBinary(binary_name)
                return self.sumo_binary
            except Exception:
                pass

        self.sumo_binary = "sumo"
        return self.sumo_binary

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Resets the SUMO simulation and restarts the TraCI physics process.
        Returns initial observation and info dict containing ground truth positions.
        """
        super().reset(seed=seed)
        self.current_step = 0
        self.close()

        cmd = [
            self.sumo_binary,
            "-c", self.sumocfg_path,
            "--step-length", str(self.step_length),
            "--no-step-log", "true",
            "--collision.action", "none",
            "--time-to-teleport", "-1",
            "--start",
            "--quit-on-end",
        ]

        logger.info(f"Launching SUMO physics process: {' '.join(cmd[:4])} ... (label: {self.traci_label})")
        try:
            traci.start(cmd, label=self.traci_label)
            self.conn = traci.getConnection(self.traci_label)
            self.is_connected = True
        except Exception as e:
            logger.error(f"Failed to start TraCI connection: {e}")
            raise e

        obs = self._get_observation()
        info = self._get_info()
        return obs, info

    def step(
        self,
        action: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Advances the SUMO physics simulation by one step, applies TLS phase actions,
        and retrieves real ground-truth vehicle coordinates from TraCI.
        """
        if not self.is_connected or self.conn is None:
            raise RuntimeError("TraCI simulation is not running. Call reset() first.")

        self.current_step += 1

        # Apply action to traffic light phases if provided
        if action is not None:
            for idx, tls_id in enumerate(self.tls_ids):
                if idx < len(action):
                    phase_idx = int(action[idx]) % 4
                    try:
                        self.conn.trafficlight.setPhase(tls_id, phase_idx)
                    except Exception:
                        pass

        # Step microscopic physics forward
        self.conn.simulationStep()

        obs = self._get_observation()
        info = self._get_info()

        # Compute dual-objective reward with temporal gating
        upstream_queues = {tls: float(obs[i * self.features_per_node] + obs[i * self.features_per_node + 1]) for i, tls in enumerate(self.tls_ids)}
        
        # Check suspect vehicle containment state
        target_contained = False
        distance_to_trap = 500.0
        gt_vehicles = info.get("ground_truth_vehicles", {})
        if self.containment_target_plate in gt_vehicles:
            target_pos = gt_vehicles[self.containment_target_plate]["position"]
            trap_x, trap_y = 380.0, 380.0  # Intersection C2 (row 2, col 2)
            distance_to_trap = float(np.hypot(target_pos[0] - trap_x, target_pos[1] - trap_y))
            if distance_to_trap < 25.0 and gt_vehicles[self.containment_target_plate]["speed"] < 1.0:
                target_contained = True

        composite_reward, r_traffic, r_security = self.reward_shaper.compute_composite_reward(
            threat_mode=self.threat_mode,
            upstream_queues=upstream_queues,
            target_contained=target_contained,
            distance_to_trap=distance_to_trap,
        )

        info["r_traffic"] = r_traffic
        info["r_security"] = r_security
        info["composite_reward"] = composite_reward
        info["threat_mode"] = self.threat_mode

        terminated = bool(self.current_step >= self.max_steps)
        truncated = False

        return obs, composite_reward, terminated, truncated, info

    def inject_emergency_vehicle(
        self,
        vehicle_id: str = "AMB_01",
        corridor_row: int = 1,
    ) -> bool:
        """Injects a physical ambulance into the TraCI simulation along a designated corridor."""
        if not self.is_connected or self.conn is None:
            return False
        try:
            route_id = f"flow_we_{corridor_row}"
            from_edge = f"left{corridor_row}A{corridor_row}"
            to_edge = f"D{corridor_row}right{corridor_row}"
            
            # Create unique route if needed
            r_id = f"route_{vehicle_id}"
            try:
                self.conn.route.add(r_id, [from_edge, to_edge])
            except Exception:
                r_id = route_id

            self.conn.vehicle.add(
                vehID=vehicle_id,
                routeID=r_id,
                typeID="ambulance",
                depart="now",
                departLane="best",
                departSpeed="max",
            )
            self.conn.vehicle.setColor(vehicle_id, (255, 30, 30, 255))
            logger.warning(f"[TraCI] Injected Emergency Vehicle [{vehicle_id}] into SUMO on {from_edge} -> {to_edge}")
            return True
        except Exception as e:
            logger.error(f"[TraCI] Error injecting emergency vehicle: {e}")
            return False

    def inject_suspect_vehicle(
        self,
        vehicle_id: str = "SUSPECT-892",
        corridor_row: int = 2,
    ) -> bool:
        """Injects a tracked suspect vehicle into the TraCI simulation."""
        if not self.is_connected or self.conn is None:
            return False
        try:
            from_edge = f"left{corridor_row}A{corridor_row}"
            to_edge = f"D{corridor_row}right{corridor_row}"
            r_id = f"route_{vehicle_id}"
            try:
                self.conn.route.add(r_id, [from_edge, to_edge])
            except Exception:
                r_id = f"flow_we_{corridor_row}"

            self.conn.vehicle.add(
                vehID=vehicle_id,
                routeID=r_id,
                typeID="suspect",
                depart="now",
                departLane="best",
                departSpeed="max",
            )
            self.conn.vehicle.setColor(vehicle_id, (245, 158, 11, 255))
            logger.warning(f"[TraCI] Injected Suspect Vehicle [{vehicle_id}] into SUMO on {from_edge} -> {to_edge}")
            return True
        except Exception as e:
            logger.error(f"[TraCI] Error injecting suspect vehicle: {e}")
            return False

    def set_containment_lockdown(self, target_tls: str = "C2"):
        """Forces an all-red containment barrier on a specific intersection via TraCI."""
        if not self.is_connected or self.conn is None:
            return
        try:
            # Set all-red phase or stopping phase
            self.conn.trafficlight.setPhase(target_tls, 1)  # Red phase
            logger.warning(f"[TraCI] Signal barrier enforced at intersection {target_tls}!")
        except Exception as e:
            logger.error(f"[TraCI] Failed to lock TLS {target_tls}: {e}")

    def set_threat_flag(self, active: bool):
        """Injected by Tier-2 Orchestrator to switch m(t) between 0 and 1."""
        self.threat_mode = 1 if active else 0
        logger.warning(f"[TraCI Env] Threat Mode Flag m(t) set to {self.threat_mode}")

    def _get_observation(self) -> np.ndarray:
        """
        Extracts augmented observation vector (16 * 7 = 112 features):
          For each intersection node (r, c):
            [q_approach_ew, q_approach_ns, q_neighbor_N, q_neighbor_S, q_neighbor_E, q_neighbor_W, m(t)]
        """
        obs = np.zeros((self.total_obs_dim,), dtype=np.float32)
        if not self.is_connected or self.conn is None:
            return obs

        # 1. First pass: extract local approach halting queues for 4x4 grid
        node_queues: Dict[Tuple[int, int], Tuple[float, float]] = {}
        for r_idx in range(4):
            for c_idx in range(4):
                tls_id = f"{self.grid_rows[r_idx]}{c_idx}"
                q_ew, q_ns = 0.0, 0.0
                try:
                    lanes = self.conn.trafficlight.getControlledLanes(tls_id)
                    if len(lanes) >= 2:
                        q_ew = float(self.conn.lane.getLastStepHaltingNumber(lanes[0]))
                        q_ns = float(self.conn.lane.getLastStepHaltingNumber(lanes[1]))
                except Exception:
                    pass
                node_queues[(r_idx, c_idx)] = (q_ew, q_ns)

        # 2. Second pass: construct augmented vector with P2P neighbor queues & m(t)
        m_val = float(self.threat_mode)
        for r_idx in range(4):
            for c_idx in range(4):
                idx = (r_idx * 4 + c_idx) * self.features_per_node
                q_ew, q_ns = node_queues.get((r_idx, c_idx), (0.0, 0.0))

                # P2P Neighbor messages (sum of queues from adjacent intersections)
                q_neighbor_N = sum(node_queues.get((r_idx + 1, c_idx), (0.0, 0.0))) if r_idx + 1 < 4 else 0.0
                q_neighbor_S = sum(node_queues.get((r_idx - 1, c_idx), (0.0, 0.0))) if r_idx - 1 >= 0 else 0.0
                q_neighbor_E = sum(node_queues.get((r_idx, c_idx + 1), (0.0, 0.0))) if c_idx + 1 < 4 else 0.0
                q_neighbor_W = sum(node_queues.get((r_idx, c_idx - 1), (0.0, 0.0))) if c_idx - 1 >= 0 else 0.0

                obs[idx + 0] = q_ew
                obs[idx + 1] = q_ns
                obs[idx + 2] = q_neighbor_N
                obs[idx + 3] = q_neighbor_S
                obs[idx + 4] = q_neighbor_E
                obs[idx + 5] = q_neighbor_W
                obs[idx + 6] = m_val

        return obs

    def _get_info(self) -> Dict[str, Any]:
        """
        Reads microscopic ground-truth vehicle coordinates directly from TraCI:
          - traci.vehicle.getPosition()
          - traci.vehicle.getSpeed()
          - traci.vehicle.getLaneID()
          - traci.vehicle.getTypeID()
        """
        ground_truth_vehicles: Dict[str, Dict[str, Any]] = {}
        if not self.is_connected or self.conn is None:
            return {"ground_truth_vehicles": {}}

        try:
            veh_ids = self.conn.vehicle.getIDList()
            for vid in veh_ids:
                # Real TraCI ground truth extraction
                pos = self.conn.vehicle.getPosition(vid)
                speed = self.conn.vehicle.getSpeed(vid)
                lane_id = self.conn.vehicle.getLaneID(vid)
                vtype = self.conn.vehicle.getTypeID(vid)

                ground_truth_vehicles[vid] = {
                    "id": vid,
                    "position": (float(pos[0]), float(pos[1])),
                    "speed": float(speed),
                    "lane_id": str(lane_id),
                    "type": str(vtype),
                }

            sim_time = self.conn.simulation.getTime()
        except Exception as e:
            logger.error(f"[TraCI] Error extracting ground truth: {e}")
            sim_time = float(self.current_step)

        return {
            "ground_truth_vehicles": ground_truth_vehicles,
            "vehicle_count": len(ground_truth_vehicles),
            "sim_time": sim_time,
            "step": self.current_step,
        }

    def close(self):
        """Safely terminates the active TraCI connection."""
        if self.is_connected and self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.is_connected = False
            self.conn = None
            logger.info("Closed TraCI simulation connection.")
