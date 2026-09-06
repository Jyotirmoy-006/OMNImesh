import unittest
import time
from omnimesh.tier1_edge.zspf_state_machine import ZSPFStateMachine, OperationalMode

class TestZSPFTransitions(unittest.TestCase):
    def test_zspf_heartbeat_timeout(self):
        zspf = ZSPFStateMachine(heartbeat_timeout=1.0, broker_timeout=3.0)
        self.assertEqual(zspf.current_mode, OperationalMode.MODE_0_FULL_MESH)

        # Advance time past heartbeat timeout
        now = time.time() + 1.5
        mode = zspf.evaluate_liveness(now)
        self.assertEqual(mode, OperationalMode.MODE_1_AUTONOMOUS_P2P)

    def test_zspf_default_3s_timeout(self):
        # Default 3.0s heartbeat timeout requirement
        zspf = ZSPFStateMachine()
        self.assertEqual(zspf.heartbeat_timeout, 3.0)
        self.assertEqual(zspf.current_mode, OperationalMode.MODE_0_FULL_MESH)

        # Under 3.0s (e.g. 2.0s), remains in Mode 0
        now = time.time() + 2.0
        self.assertEqual(zspf.evaluate_liveness(now), OperationalMode.MODE_0_FULL_MESH)

        # Over 3.0s (e.g. 3.2s), transitions to Mode 1
        now = time.time() + 3.2
        self.assertEqual(zspf.evaluate_liveness(now), OperationalMode.MODE_1_AUTONOMOUS_P2P)

    def test_zspf_mqtt_disconnect_entirely(self):
        # Entire MQTT client disconnection forces Mode 2 (Max-Pressure Island)
        zspf = ZSPFStateMachine()
        self.assertEqual(zspf.current_mode, OperationalMode.MODE_0_FULL_MESH)

        zspf.notify_broker_disconnected()
        self.assertEqual(zspf.current_mode, OperationalMode.MODE_2_ISLAND)
        self.assertEqual(zspf.evaluate_liveness(time.time()), OperationalMode.MODE_2_ISLAND)

    def test_zspf_broker_timeout(self):
        zspf = ZSPFStateMachine(heartbeat_timeout=1.0, broker_timeout=2.0)
        now = time.time() + 2.5
        mode = zspf.evaluate_liveness(now)
        self.assertEqual(mode, OperationalMode.MODE_2_ISLAND)

    def test_zspf_heartbeat_restoration(self):
        zspf = ZSPFStateMachine(heartbeat_timeout=1.0, broker_timeout=5.0)
        now = time.time() + 1.5
        self.assertEqual(zspf.evaluate_liveness(now), OperationalMode.MODE_1_AUTONOMOUS_P2P)

        # Heartbeat restored
        zspf.record_heartbeat(timestamp=now)
        self.assertEqual(zspf.current_mode, OperationalMode.MODE_0_FULL_MESH)

if __name__ == "__main__":
    unittest.main()
