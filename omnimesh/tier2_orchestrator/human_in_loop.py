from omnimesh.utils.logger import logger

class HumanInTheLoopGateway:
    """
    Enforces ethical and legal compliance by requiring operator confirmation
    before physical traffic containment barriers are actuated.
    """
    def __init__(self, auto_approve_for_sim: bool = False):
        self.auto_approve_for_sim = auto_approve_for_sim

    def request_authorization(self, plate: str, location: str, confidence: float) -> bool:
        logger.warning(f"ETHICAL GATEWAY: Suspect plate '{plate}' at '{location}' with confidence {confidence:.2f}")
        if self.auto_approve_for_sim:
            logger.info("Human-in-the-loop authorization granted (Sim Auto-Approve).")
            return True
        # In real deployments, blocks until operator clicks confirm
        return False
