from typing import List, Dict, Any
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
    """
    def __init__(self, node_id: str, incoming_lanes: List[str], num_phases: int = 4):
        self.node_id = node_id
        self.state_manager = LaneQueueStateManager(node_id, incoming_lanes)
        self.policy = LightweightPolicy(state_dim=len(incoming_lanes)*2 + 1, action_dim=num_phases)
        self.zspf = ZSPFStateMachine()
        self.current_phase = 0
        self.green_wave_active = False

    def step(self, current_time: float, neighbor_states: Dict[str, Any] = None) -> int:
        mode = self.zspf.evaluate_liveness(current_time)
        state_vec = self.state_manager.get_local_state_vector()

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
