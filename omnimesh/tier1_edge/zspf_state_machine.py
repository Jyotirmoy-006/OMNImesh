"""
Omni-Mesh Zero Single Point of Failure (ZSPF) State Machine
Enforces deterministic failover hierarchy (Mode 0 -> Mode 1 -> Mode 2)
evaluating heartbeat liveness and MQTT broker connection status.
"""

from enum import IntEnum
import time
from typing import Optional
from omnimesh.utils.logger import logger

class OperationalMode(IntEnum):
    MODE_0_FULL_MESH = 0       # Tier 2 online, Global RL + Orchestrator directives
    MODE_1_AUTONOMOUS_P2P = 1  # Tier 2 offline, pure MARL via local MQTT P2P
    MODE_2_ISLAND = 2          # Broker offline, localized Max-Pressure fallback

class ZSPFStateMachine:
    """
    Manages Zero Single Point of Failure (ZSPF) transitions:
    - Mode 0: Global Mesh (heartbeat < 3.0s, broker connected)
    - Mode 1: Autonomous P2P (heartbeat > 3.0s, broker connected)
    - Mode 2: Island Max-Pressure (broker disconnected entirely or timeout)
    """

    def __init__(self, heartbeat_timeout: float = 3.0, broker_timeout: float = 5.0):
        self.heartbeat_timeout = float(heartbeat_timeout)
        self.broker_timeout = float(broker_timeout)
        self.current_mode = OperationalMode.MODE_0_FULL_MESH
        
        # Track timestamp of the last received heartbeat
        now = time.time()
        self.last_heartbeat = now
        self.last_orchestrator_heartbeat = now
        self.last_broker_ack = now
        self.is_broker_connected = True

    def record_heartbeat(self, timestamp: Optional[float] = None):
        """Records an incoming Tier-2 Orchestrator heartbeat timestamp."""
        ts = timestamp if timestamp is not None else time.time()
        self.last_heartbeat = ts
        self.last_orchestrator_heartbeat = ts
        self.last_broker_ack = ts  # Heartbeat arriving over MQTT confirms broker liveness
        
        # Restore to Mode 0 if we were in Mode 1 and broker is healthy
        if self.is_broker_connected and self.current_mode == OperationalMode.MODE_1_AUTONOMOUS_P2P:
            logger.info("Orchestrator heartbeat restored. Transitioning Mode 1 -> Mode 0 (Full Mesh).")
            self.current_mode = OperationalMode.MODE_0_FULL_MESH

    def record_orchestrator_heartbeat(self, timestamp: Optional[float] = None):
        """Alias for backward compatibility."""
        self.record_heartbeat(timestamp=timestamp)

    def record_broker_ack(self, timestamp: Optional[float] = None):
        """Records an active broker acknowledgment."""
        self.last_broker_ack = timestamp if timestamp is not None else time.time()
        self.is_broker_connected = True
        if self.current_mode == OperationalMode.MODE_2_ISLAND:
            logger.info("Broker connectivity restored. Transitioning Mode 2 -> Mode 1 (Autonomous P2P).")
            self.current_mode = OperationalMode.MODE_1_AUTONOMOUS_P2P

    def notify_broker_disconnected(self):
        """
        Invoked immediately when MQTT client disconnects entirely.
        Forces instant failover transition to Mode 2 (Max-Pressure Island).
        """
        self.is_broker_connected = False
        if self.current_mode != OperationalMode.MODE_2_ISLAND:
            logger.warning("MQTT client disconnected entirely. Instant transition to Mode 2 (Max-Pressure Island).")
            self.current_mode = OperationalMode.MODE_2_ISLAND

    def notify_broker_connected(self):
        """Invoked when MQTT client successfully re-establishes connection."""
        self.is_broker_connected = True
        self.last_broker_ack = time.time()
        now = time.time()
        if (now - self.last_heartbeat) <= self.heartbeat_timeout:
            self.current_mode = OperationalMode.MODE_0_FULL_MESH
            logger.info("Broker reconnected with fresh heartbeat. Mode 2 -> Mode 0 (Full Mesh).")
        else:
            self.current_mode = OperationalMode.MODE_1_AUTONOMOUS_P2P
            logger.info("Broker reconnected without active heartbeat. Mode 2 -> Mode 1 (Autonomous P2P).")

    def evaluate_liveness(self, current_time: Optional[float] = None) -> OperationalMode:
        """
        Evaluates active liveness metrics:
          1. If MQTT client is disconnected entirely -> Mode 2 (Max-Pressure Island).
          2. If broker_dt > broker_timeout -> Mode 2 (Max-Pressure Island).
          3. If time.time() - last_heartbeat > 3.0s -> Mode 1 (Autonomous P2P).
          4. Otherwise, if heartbeat is fresh -> Mode 0 (Full Mesh).
        """
        if current_time is None:
            current_time = time.time()

        # Rule 1: Entire MQTT disconnect forces Mode 2
        if not self.is_broker_connected:
            if self.current_mode != OperationalMode.MODE_2_ISLAND:
                logger.warning("MQTT client disconnected entirely. Transitioning to Mode 2 (Max-Pressure Island).")
                self.current_mode = OperationalMode.MODE_2_ISLAND
            return self.current_mode

        broker_dt = current_time - self.last_broker_ack
        if broker_dt > self.broker_timeout:
            if self.current_mode != OperationalMode.MODE_2_ISLAND:
                logger.warning(
                    f"Broker timeout ({broker_dt:.1f}s > {self.broker_timeout:.1f}s). "
                    f"Falling back to Mode 2 (Island Max-Pressure)."
                )
                self.current_mode = OperationalMode.MODE_2_ISLAND
            return self.current_mode

        # Rule 2: Heartbeat timeout (> 3.0s) forces Mode 1
        heartbeat_dt = current_time - self.last_heartbeat
        if heartbeat_dt > self.heartbeat_timeout:
            if self.current_mode == OperationalMode.MODE_0_FULL_MESH:
                logger.warning(
                    f"Orchestrator heartbeat lost ({heartbeat_dt:.1f}s > {self.heartbeat_timeout:.1f}s). "
                    f"Degrading to Mode 1 (Autonomous P2P)."
                )
                self.current_mode = OperationalMode.MODE_1_AUTONOMOUS_P2P
        elif self.current_mode == OperationalMode.MODE_1_AUTONOMOUS_P2P:
            # Heartbeat recovered
            logger.info("Orchestrator heartbeat received. Restoring Mode 1 -> Mode 0 (Full Mesh).")
            self.current_mode = OperationalMode.MODE_0_FULL_MESH

        return self.current_mode
