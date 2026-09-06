import time
from typing import List, Dict, Any
from omnimesh.utils.logger import logger
from .watchlist_manager import WatchlistManager
from .rule_engine import ContainmentRuleEngine
from .human_in_loop import HumanInTheLoopGateway

class GlobalZoneOrchestrator:
    """
    Tier-2 Global Agent supervising macro anomalies, heartbeat generation,
    and ANPR containment authorization.
    """
    def __init__(self, zone_id: str, auto_approve_sim: bool = True):
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
        logger.warning(f"Orchestrator received multi-node verified alert for plate: {plate} at {confirmed_nodes}")
        if self.hitl_gateway.request_authorization(plate, str(confirmed_nodes), confidence):
            target_node = confirmed_nodes[-1]
            return self.rule_engine.compute_containment_directives(target_node, [])
        return {}
