import time
from typing import List, Dict, Any, Optional
from omnimesh.utils.logger import logger
from .watchlist_manager import WatchlistManager
from .rule_engine import ContainmentRuleEngine
from .human_in_loop import HumanInTheLoopGateway

class GlobalZoneOrchestrator:
    """
    Tier-2 Global Agent supervising macro anomalies, heartbeat generation,
    and ANPR containment authorization under ethical Human-in-the-Loop governance.
    """
    def __init__(self, zone_id: str, auto_approve_sim: bool = False):
        self.zone_id = zone_id
        self.watchlist_mgr = WatchlistManager()
        self.rule_engine = ContainmentRuleEngine()
        self.hitl_gateway = HumanInTheLoopGateway(auto_approve_for_sim=auto_approve_sim)
        self.last_heartbeat_sent = time.time()

    def generate_heartbeat(self) -> Dict[str, Any]:
        self.last_heartbeat_sent = time.time()
        return {
            "zone_id": self.zone_id,
            "timestamp": self.last_heartbeat_sent,
            "type": "HEARTBEAT",
        }

    def process_consensus_alert(self, plate: str, confirmed_nodes: List[str], confidence: float) -> Dict[str, int]:
        """
        Processes 2-node consensus sightings.
        Blocks signal override output if HITL gateway returns False (state=PENDING_AUTHORIZATION).
        """
        logger.warning(f"Orchestrator received multi-node verified alert for plate: {plate} at {confirmed_nodes}")
        authorized = self.hitl_gateway.request_authorization(
            plate=plate,
            location=str(confirmed_nodes),
            confidence=confidence,
            confirmed_nodes=confirmed_nodes,
        )
        if authorized:
            target_node = confirmed_nodes[-1]
            return self.rule_engine.compute_containment_directives(target_node, [])
        return {}

    def authorize_containment(self, approver_id: str = "dispatcher_lead") -> Dict[str, int]:
        """
        Unlocks the HITL gate and executes the computed containment barrier directives.
        """
        auth_result = self.hitl_gateway.authorize(approver_id=approver_id)
        alert = auth_result.get("alert") or {}
        confirmed_nodes = alert.get("confirmed_nodes", ["node_2_2"])
        target_node = confirmed_nodes[-1] if confirmed_nodes else "node_2_2"
        return self.rule_engine.compute_containment_directives(target_node, [])
