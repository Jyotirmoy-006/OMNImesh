"""
Dual-Objective Temporally Gated Reward Shaping Module for Omni-Mesh
Implements:
  r_i(t) = (1 - m(t)) * r_i^{traffic} + m(t) * r_i^{security}
where m(t) in {0, 1} is the binary threat flag injected by the Tier-2 Orchestrator,
and r_i^{traffic} is derived from Max-Pressure control principles.
"""

from typing import Dict, Optional, List, Tuple
import numpy as np

class DualObjectiveRewardShaper:
    """
    Computes temporally gated composite rewards balancing civilian traffic flow
    (Max-Pressure optimization) with high-priority security and containment overrides.
    """
    def __init__(
        self,
        default_capacity_per_lane: float = 25.0,
        pressure_weight: float = 1.0,
        security_contain_reward: float = 100.0,
        security_proximity_weight: float = 2.0,
        security_breakout_penalty: float = -200.0,
    ):
        self.default_capacity_per_lane = default_capacity_per_lane
        self.pressure_weight = pressure_weight
        self.security_contain_reward = security_contain_reward
        self.security_proximity_weight = security_proximity_weight
        self.security_breakout_penalty = security_breakout_penalty

    def compute_max_pressure_traffic_reward(
        self,
        upstream_queues: Dict[str, float],
        downstream_queues: Optional[Dict[str, float]] = None,
        downstream_capacities: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Calculates civilian traffic reward using Max-Pressure logic:
          Pressure(l) = q_upstream(l) - q_downstream(l)
          or queue density relative to downstream available capacity:
          available_capacity = max(0, capacity - q_downstream)
          pressure = q_upstream - available_capacity
        Maximizing throughput corresponds to minimizing total network pressure.
        Reward is negative total pressure: -sum(max(0, pressure)).
        """
        total_pressure = 0.0

        for lane_id, q_up in upstream_queues.items():
            cap = (
                downstream_capacities.get(lane_id, self.default_capacity_per_lane)
                if downstream_capacities
                else self.default_capacity_per_lane
            )
            q_down = (
                downstream_queues.get(lane_id, 0.0)
                if downstream_queues
                else 0.0
            )

            # Available downstream capacity buffer
            downstream_avail = max(0.0, cap - q_down)
            
            # Differential pressure: excess queue over downstream absorption capacity
            lane_pressure = max(0.0, q_up - downstream_avail)
            total_pressure += lane_pressure

        # Base traffic reward: negative weighted pressure
        r_traffic = -float(self.pressure_weight * total_pressure)
        return r_traffic

    def compute_security_containment_reward(
        self,
        target_contained: bool,
        distance_to_trap: float,
        unauthorized_breakout: bool = False,
        barrier_active: bool = True,
    ) -> float:
        """
        Calculates the high-priority security override reward:
          - High positive bonus upon successful containment inside designated perimeter
          - Distance-based guidance shaping toward the trap zone
          - Severe penalty if suspect vehicle breaches the perimeter
        """
        if unauthorized_breakout:
            return self.security_breakout_penalty

        if target_contained:
            return self.security_contain_reward

        # Proximity shaping reward (closer to barrier trap = higher reward)
        proximity_bonus = -float(self.security_proximity_weight * np.log1p(max(0.0, distance_to_trap)))
        return proximity_bonus if barrier_active else 0.0

    def compute_composite_reward(
        self,
        threat_mode: int,
        upstream_queues: Dict[str, float],
        downstream_queues: Optional[Dict[str, float]] = None,
        target_contained: bool = False,
        distance_to_trap: float = 0.0,
        unauthorized_breakout: bool = False,
        downstream_capacities: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float, float]:
        """
        Mathematically enforces the temporally gated composite reward:
          r_i(t) = (1 - m(t)) * r_i^{traffic} + m(t) * r_i^{security}
        where m(t) in {0, 1} is the binary threat flag.

        Returns:
          (composite_reward, r_traffic, r_security)
        """
        m_t = 1.0 if int(threat_mode) > 0 else 0.0

        r_traffic = self.compute_max_pressure_traffic_reward(
            upstream_queues=upstream_queues,
            downstream_queues=downstream_queues,
            downstream_capacities=downstream_capacities,
        )

        r_security = self.compute_security_containment_reward(
            target_contained=target_contained,
            distance_to_trap=distance_to_trap,
            unauthorized_breakout=unauthorized_breakout,
        )

        # Temporal priority gating
        composite_reward = float((1.0 - m_t) * r_traffic + m_t * r_security)

        return composite_reward, r_traffic, r_security
