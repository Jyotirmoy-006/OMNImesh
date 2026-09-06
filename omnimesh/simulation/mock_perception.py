"""
Mock Perception Layer for Omni-Mesh
Wraps TraCI ground-truth simulation outputs, injects Gaussian detection noise
(μ=0.98, σ=0.03), and simulates Raspberry Pi 4B thermal throttling dropout.
"""

from typing import Dict, List, Any, Optional
import numpy as np
from omnimesh.utils.logger import logger

class MockPerception:
    """
    Perception interface wrapping TraCI simulation telemetry.
    Applies Gaussian noise and hardware thermal degradation dropout before
    feeding observations to Tier-1 Edge Agents.
    """
    def __init__(
        self,
        mean_accuracy: float = 0.98,
        std_accuracy: float = 0.03,
        dropout_base_prob: float = 0.02,
        throttled_dropout_prob: float = 0.40,
    ):
        self.mean_accuracy = mean_accuracy
        self.std_accuracy = std_accuracy
        self.dropout_base_prob = dropout_base_prob
        self.throttled_dropout_prob = throttled_dropout_prob
        self.thermal_throttle: bool = False
        self.current_cpu_temp: float = 54.0

    def set_thermal_state(self, temp_c: float, throttled: Optional[bool] = None):
        """Updates simulated hardware temperature and throttling state."""
        self.current_cpu_temp = temp_c
        if throttled is not None:
            self.thermal_throttle = throttled
        else:
            self.thermal_throttle = (temp_c >= 80.0)

    def process_ground_truth(
        self,
        ground_truth_vehicles: Dict[str, Dict[str, Any]],
        intersections: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Processes real TraCI vehicle states:
          1. Injects Gaussian noise: N(μ=0.98, σ=0.03)
          2. Randomly drops out detections if thermal_throttle is active
          3. Computes noisy lane queues and feeds Edge Agents
        """
        detected_vehicles = {}
        dropout_rate = (
            self.throttled_dropout_prob if self.thermal_throttle else self.dropout_base_prob
        )

        dropped_count = 0
        for veh_id, data in ground_truth_vehicles.items():
            # Thermal throttle detection dropout simulation
            if np.random.rand() < dropout_rate:
                dropped_count += 1
                continue

            # Gaussian noise injection on detection confidence / presence
            noise_factor = float(np.random.normal(self.mean_accuracy, self.std_accuracy))
            noise_factor = float(np.clip(noise_factor, 0.70, 1.05))

            pos = data.get("position", (0.0, 0.0))
            noisy_x = pos[0] + float(np.random.normal(0, 0.5)) if not self.thermal_throttle else pos[0] + float(np.random.normal(0, 2.5))
            noisy_y = pos[1] + float(np.random.normal(0, 0.5)) if not self.thermal_throttle else pos[1] + float(np.random.normal(0, 2.5))

            detected_vehicles[veh_id] = {
                "id": veh_id,
                "position": (noisy_x, noisy_y),
                "speed": max(0.0, data.get("speed", 0.0) * noise_factor),
                "lane_id": data.get("lane_id", ""),
                "type": data.get("type", "civilian"),
                "confidence": noise_factor,
            }

        if self.thermal_throttle and dropped_count > 0:
            logger.warning(
                f"[PERCEPTION THROTTLED @ {self.current_cpu_temp:.1f}°C] Dropped {dropped_count}/{len(ground_truth_vehicles)} vehicle detections."
            )

        # Aggregate queue densities per intersection for edge agents
        node_queue_updates = self._estimate_node_queues(detected_vehicles, intersections)

        return {
            "detected_vehicles": detected_vehicles,
            "dropped_count": dropped_count,
            "thermal_throttled": self.thermal_throttle,
            "cpu_temp": self.current_cpu_temp,
            "node_queues": node_queue_updates,
        }

    def _estimate_node_queues(
        self,
        detected_vehicles: Dict[str, Dict[str, Any]],
        intersections: Dict[str, Any],
    ) -> Dict[str, Dict[str, float]]:
        """
        Maps detected vehicles to nearest intersection approach lanes,
        updating the edge agent state manager.
        """
        node_queues: Dict[str, Dict[str, float]] = {}

        for nid, node_info in intersections.items():
            nx = node_info.get("x", 0.0)
            ny = node_info.get("y", 0.0)
            q_ew = 0.0
            q_ns = 0.0

            for v in detected_vehicles.values():
                vx, vy = v["position"]
                dist = np.hypot(vx - nx, vy - ny)
                if dist < 60.0:  # Within detection zone
                    if abs(vx - nx) > abs(vy - ny):
                        q_ew += 1.0
                    else:
                        q_ns += 1.0

            node_queues[nid] = {"EW": q_ew, "NS": q_ns}

            # Update the underlying edge agent's state manager directly
            agent = node_info.get("agent")
            if agent and hasattr(agent, "state_manager"):
                agent.state_manager.update_from_vision({
                    "queues": {
                        "east": q_ew / 2.0,
                        "west": q_ew / 2.0,
                        "north": q_ns / 2.0,
                        "south": q_ns / 2.0,
                    }
                })

        return node_queues
