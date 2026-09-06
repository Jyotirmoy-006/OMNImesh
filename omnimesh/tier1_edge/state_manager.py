from typing import Dict, List, Any
import numpy as np

class LaneQueueStateManager:
    """
    Aggregates vision detection results, lane queue lengths,
    and neighbor state vectors into a unified observation vector.
    """
    def __init__(self, node_id: str, incoming_lanes: List[str]):
        self.node_id = node_id
        self.incoming_lanes = incoming_lanes
        self.queue_lengths: Dict[str, float] = {lane: 0.0 for lane in incoming_lanes}
        self.wait_times: Dict[str, float] = {lane: 0.0 for lane in incoming_lanes}
        self.threat_active_flag: int = 0

    def update_from_vision(self, detection_summary: Dict[str, Any]):
        for lane, q in detection_summary.get("queues", {}).items():
            if lane in self.queue_lengths:
                self.queue_lengths[lane] = float(q)

    def set_threat_flag(self, active: bool):
        self.threat_active_flag = 1 if active else 0

    def get_local_state_vector(self) -> np.ndarray:
        # [queues..., wait_times..., threat_flag]
        q_vals = [self.queue_lengths[l] for l in self.incoming_lanes]
        w_vals = [self.wait_times[l] for l in self.incoming_lanes]
        return np.array(q_vals + w_vals + [float(self.threat_active_flag)], dtype=np.float32)
