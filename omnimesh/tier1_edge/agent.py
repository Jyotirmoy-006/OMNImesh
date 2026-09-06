from typing import List, Dict, Any, Optional
import queue
from queue import Empty
import multiprocessing
import numpy as np
from omnimesh.utils.logger import logger
from .state_manager import LaneQueueStateManager
from .policy import LightweightPolicy
from .zspf_state_machine import ZSPFStateMachine, OperationalMode

class EdgeNodeAgent:
    """
    Tier-1 Edge Agent deployed at an individual intersection.
    Executes local control policies, negotiates P2P Green Waves,
    and supports active ZSPF degradation.
    Fetches state updates from high-frequency perception via an IPC Queue
    using non-blocking reads with clean queue.Empty fallback.
    """
    def __init__(
        self,
        node_id: str,
        incoming_lanes: List[str],
        num_phases: int = 4,
        ipc_queue: Optional[multiprocessing.Queue] = None,
    ):
        self.node_id = node_id
        self.incoming_lanes = incoming_lanes
        self.state_manager = LaneQueueStateManager(node_id, incoming_lanes)
        self.policy = LightweightPolicy(state_dim=len(incoming_lanes) * 2 + 1, action_dim=num_phases)
        self.zspf = ZSPFStateMachine()
        self.current_phase = 0
        self.green_wave_active = False

        # IPC Queue for decoupled perception loop (Process A -> Process C)
        self.ipc_queue: Optional[multiprocessing.Queue] = ipc_queue

        # Cache for last known state (fallback when perception lags or queue is empty)
        self.last_known_state: np.ndarray = self.state_manager.get_local_state_vector()
        self.last_perception_timestamp: float = 0.0

    def set_ipc_queue(self, ipc_queue: multiprocessing.Queue):
        """Attaches or updates the IPC queue for non-blocking perception state consumption."""
        self.ipc_queue = ipc_queue

    def fetch_perception_state(self) -> bool:
        """
        Fetches the latest state from the IPC queue using non-blocking get_nowait().
        Handles queue.Empty cleanly, falling back to the last known state if the
        perception process lags or if no new frame has been pushed.
        """
        if self.ipc_queue is None:
            return False

        latest_frame: Optional[Dict[str, Any]] = None
        try:
            # Drain non-blocking to retrieve the freshest available perception state
            while True:
                try:
                    latest_frame = self.ipc_queue.get_nowait()
                except (Empty, queue.Empty):
                    break
        except (Empty, queue.Empty):
            latest_frame = None

        if latest_frame is not None:
            self._apply_perception_update(latest_frame)
            return True
        else:
            # Clean fallback to last known state if perception process lags
            return False

    def _apply_perception_update(self, frame_data: Dict[str, Any]):
        """Updates internal state manager with data received over IPC."""
        node_queues = frame_data.get("node_queues", {})
        node_data = node_queues.get(self.node_id)
        if node_data:
            if "queues" in node_data:
                self.state_manager.update_from_vision({"queues": node_data["queues"]})
            elif "EW" in node_data and "NS" in node_data:
                ew = float(node_data["EW"])
                ns = float(node_data["NS"])
                self.state_manager.update_from_vision({
                    "queues": {
                        "east": ew / 2.0,
                        "west": ew / 2.0,
                        "north": ns / 2.0,
                        "south": ns / 2.0,
                    }
                })
        self.last_known_state = self.state_manager.get_local_state_vector()
        self.last_perception_timestamp = frame_data.get("timestamp", 0.0)

    def step(self, current_time: float, neighbor_states: Dict[str, Any] = None) -> int:
        """
        Executes one RL Control loop tick.
        Fetches state non-blockingly from IPC queue (falling back to last known state if empty),
        evaluates ZSPF liveness, and chooses action.
        """
        # Constraint 3: Non-blocking fetch with queue.Empty fallback
        self.fetch_perception_state()

        mode = self.zspf.evaluate_liveness(current_time)
        state_vec = self.state_manager.get_local_state_vector()
        self.last_known_state = state_vec

        if self.green_wave_active:
            logger.info(f"[{self.node_id}] P2P Green Wave active! Enforcing priority phase.")
            return self.current_phase

        is_island = (mode == OperationalMode.MODE_2_ISLAND)
        action = self.policy.select_action(state_vec, is_island_mode=is_island)
        self.current_phase = action
        return action

    def receive_emergency_request(self, corridor_hops: List[str], target_phase: int):
        if self.node_id in corridor_hops:
            logger.warning(f"[{self.node_id}] Initiating P2P Green Wave preemption for phase {target_phase}.")
            self.green_wave_active = True
            self.current_phase = target_phase
