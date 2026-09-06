import unittest
import time
from omnimesh.tier1_edge.agent import EdgeNodeAgent
from omnimesh.tier1_edge.zspf_state_machine import OperationalMode

class TestTier1Agent(unittest.TestCase):
    def test_edge_agent_initialization(self):
        agent = EdgeNodeAgent(node_id="test_node", incoming_lanes=["l0", "l1", "l2", "l3"])
        action = agent.step(current_time=time.time())
        self.assertTrue(0 <= action < 4)

    def test_emergency_green_wave(self):
        agent = EdgeNodeAgent(node_id="node_2", incoming_lanes=["l0", "l1"])
        agent.receive_emergency_request(corridor_hops=["node_1", "node_2", "node_3"], target_phase=2)
        self.assertTrue(agent.green_wave_active)
        self.assertEqual(agent.current_phase, 2)

if __name__ == "__main__":
    unittest.main()
