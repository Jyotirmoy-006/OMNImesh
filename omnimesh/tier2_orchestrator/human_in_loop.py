"""
Human-in-the-Loop (HITL) Ethical Authorization Gateway
Maintains an internal state lock blocking physical signal containment
until an explicit dispatcher authorization trigger is received.
"""

import time
import threading
from typing import Dict, Any, List, Optional
from omnimesh.utils.logger import logger

class HumanInTheLoopGateway:
    """
    Enforces ethical and legal compliance by requiring explicit human operator
    authorization before physical traffic containment barriers are actuated.
    
    Maintains an internal state lock:
      - IDLE: No suspect vehicle under active consensus.
      - PENDING_AUTHORIZATION: Multi-node consensus confirmed; signal override BLOCKED.
      - AUTHORIZED: Operator granted permission; signal containment permitted.
      - REJECTED: Operator aborted containment.
    """
    GLOBAL_BYPASS: bool = False

    def __init__(self, auto_approve_for_sim: bool = False):
        self.auto_approve_for_sim = auto_approve_for_sim
        self.state: str = "IDLE"
        self.is_locked: bool = True
        self.pending_alert: Optional[Dict[str, Any]] = None
        self.authorization_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def request_authorization(
        self,
        plate: str,
        location: str,
        confidence: float,
        confirmed_nodes: Optional[List[str]] = None,
    ) -> bool:
        """
        Invoked when 2-node consensus is verified.
        Unless globally bypassed or auto-approved, maintains internal state lock
        and blocks signal override output (returns False).
        """
        with self._lock:
            # Constraint 4: Allow automatic bypass during headless benchmark evaluation
            if self.GLOBAL_BYPASS or self.auto_approve_for_sim:
                self.state = "AUTHORIZED"
                self.is_locked = False
                logger.info(
                    f"ETHICAL GATEWAY: Suspect plate '{plate}' automatically approved (Headless/Sim Bypass)."
                )
                return True

            # Constraint 1: Maintain internal state lock blocking signal override
            self.state = "PENDING_AUTHORIZATION"
            self.is_locked = True
            self.pending_alert = {
                "plate": plate,
                "location": location,
                "confidence": confidence,
                "confirmed_nodes": confirmed_nodes or [],
                "timestamp": time.time(),
            }
            logger.warning(
                f"[ETHICAL GATEWAY LOCK] ANPR Multi-Node Consensus confirmed for plate '{plate}' at {location}. "
                f"Signal override BLOCKED in state PENDING_AUTHORIZATION. Awaiting dispatcher confirmation."
            )
            return False

    def authorize(self, approver_id: str = "dispatcher_lead") -> Dict[str, Any]:
        """
        Unlocks the HITL state machine and permits physical signal override execution.
        """
        with self._lock:
            alert = self.pending_alert or {}
            self.state = "AUTHORIZED"
            self.is_locked = False
            auth_record = {
                "timestamp": time.time(),
                "approver_id": approver_id,
                "plate": alert.get("plate", "UNKNOWN"),
                "status": "APPROVED",
            }
            self.authorization_history.append(auth_record)
            logger.info(
                f"[ETHICAL GATEWAY UNLOCKED] Dispatcher '{approver_id}' authorized physical containment for {alert.get('plate')}."
            )
            return {
                "status": "success",
                "state": self.state,
                "is_locked": self.is_locked,
                "approver_id": approver_id,
                "alert": alert,
            }

    def reject(self, approver_id: str = "dispatcher_lead", reason: str = "False positive") -> Dict[str, Any]:
        """
        Aborts the pending containment alert.
        """
        with self._lock:
            alert = self.pending_alert or {}
            self.state = "REJECTED"
            self.is_locked = True
            reject_record = {
                "timestamp": time.time(),
                "approver_id": approver_id,
                "plate": alert.get("plate", "UNKNOWN"),
                "status": "REJECTED",
                "reason": reason,
            }
            self.authorization_history.append(reject_record)
            logger.warning(
                f"[ETHICAL GATEWAY REJECTED] Dispatcher '{approver_id}' rejected containment for {alert.get('plate')}: {reason}"
            )
            self.pending_alert = None
            return {
                "status": "rejected",
                "state": self.state,
                "is_locked": self.is_locked,
                "reason": reason,
            }

    def reset(self):
        """Resets the gateway back to IDLE state."""
        with self._lock:
            self.state = "IDLE"
            self.is_locked = True
            self.pending_alert = None

    def get_status(self) -> Dict[str, Any]:
        """Returns current HITL gateway status."""
        with self._lock:
            return {
                "state": self.state,
                "is_locked": self.is_locked,
                "pending_alert": self.pending_alert,
                "auto_approve_for_sim": self.auto_approve_for_sim,
                "global_bypass": self.GLOBAL_BYPASS,
            }
