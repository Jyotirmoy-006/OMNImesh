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

    def test_zspf_broker_timeout(self):
        zspf = ZSPFStateMachine(heartbeat_timeout=1.0, broker_timeout=2.0)
        now = time.time() + 2.5
        mode = zspf.evaluate_liveness(now)
        self.assertEqual(mode, OperationalMode.MODE_2_ISLAND)

if __name__ == "__main__":
    unittest.main()
