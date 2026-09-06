from enum import IntEnum
import time
from omnimesh.utils.logger import logger

class OperationalMode(IntEnum):
    MODE_0_FULL_MESH = 0       # Tier 2 online, Global RL + Orchestrator directives
    MODE_1_AUTONOMOUS_P2P = 1  # Tier 2 offline, pure MARL via local MQTT
    MODE_2_ISLAND = 2          # Broker offline, localized Max-Pressure fallback

class ZSPFStateMachine:
    """
    Manages Zero Single Point of Failure (ZSPF) transitions:
    Mode 0 -> Mode 1 -> Mode 2 with provable fallback bounds.
    """
    def __init__(self, heartbeat_timeout: float = 3.0, broker_timeout: float = 5.0):
        self.heartbeat_timeout = heartbeat_timeout
        self.broker_timeout = broker_timeout
        self.current_mode = OperationalMode.MODE_0_FULL_MESH
        self.last_orchestrator_heartbeat = time.time()
        self.last_broker_ack = time.time()

    def record_orchestrator_heartbeat(self):
        self.last_orchestrator_heartbeat = time.time()
        if self.current_mode == OperationalMode.MODE_1_AUTONOMOUS_P2P:
            logger.info("Orchestrator heartbeat restored. Transitioning Mode 1 -> Mode 0 (Full Mesh).")
            self.current_mode = OperationalMode.MODE_0_FULL_MESH

    def record_broker_ack(self):
        self.last_broker_ack = time.time()
        if self.current_mode == OperationalMode.MODE_2_ISLAND:
            logger.info("Broker connectivity restored. Transitioning Mode 2 -> Mode 1 (Autonomous P2P).")
            self.current_mode = OperationalMode.MODE_1_AUTONOMOUS_P2P

    def evaluate_liveness(self, current_time: float) -> OperationalMode:
        orchestrator_dt = current_time - self.last_orchestrator_heartbeat
        broker_dt = current_time - self.last_broker_ack

        if broker_dt > self.broker_timeout:
            if self.current_mode != OperationalMode.MODE_2_ISLAND:
                logger.warning(f"Broker timeout ({broker_dt:.1f}s > {self.broker_timeout}s). Falling back to Mode 2 (Island Max-Pressure).")
                self.current_mode = OperationalMode.MODE_2_ISLAND
        elif orchestrator_dt > self.heartbeat_timeout:
            if self.current_mode == OperationalMode.MODE_0_FULL_MESH:
                logger.warning(f"Orchestrator heartbeat lost ({orchestrator_dt:.1f}s > {self.heartbeat_timeout}s). Degrading to Mode 1 (Autonomous P2P).")
                self.current_mode = OperationalMode.MODE_1_AUTONOMOUS_P2P

        return self.current_mode
