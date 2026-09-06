import unittest
from omnimesh.vision.consensus import MultiNodeConsensusFilter

class TestConsensusFilter(unittest.TestCase):
    def test_multi_node_consensus(self):
        consensus = MultiNodeConsensusFilter(window_sec=5.0, required_nodes=2)
        # First sighting from node_A
        res1 = consensus.register_sighting("ABC-123", "node_A", 0.95)
        self.assertIsNone(res1)

        # Second sighting from same node should not trigger
        res2 = consensus.register_sighting("ABC-123", "node_A", 0.96)
        self.assertIsNone(res2)

        # Sighting from distinct node_B triggers consensus
        res3 = consensus.register_sighting("ABC-123", "node_B", 0.97)
        self.assertIsNotNone(res3)
        self.assertIn("node_A", res3)
        self.assertIn("node_B", res3)

if __name__ == "__main__":
    unittest.main()
