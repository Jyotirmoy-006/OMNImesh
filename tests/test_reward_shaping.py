import unittest
from omnimesh.tier1_edge.reward_shaping import DualObjectiveRewardShaper

class TestRewardShaping(unittest.TestCase):
    def setUp(self):
        self.shaper = DualObjectiveRewardShaper(
            default_capacity_per_lane=25.0,
            pressure_weight=1.0,
            security_contain_reward=100.0,
        )

    def test_pure_civilian_traffic_mode(self):
        # When threat_mode m(t) == 0, reward must strictly equal r_traffic
        upstream = {"lane_0": 10.0, "lane_1": 5.0}
        downstream = {"lane_0": 20.0, "lane_1": 5.0}  # capacity = 25
        # lane_0: avail = 25 - 20 = 5, pressure = max(0, 10 - 5) = 5
        # lane_1: avail = 25 - 5 = 20, pressure = max(0, 5 - 20) = 0
        # total pressure = 5 -> r_traffic = -5.0

        composite, r_traffic, r_security = self.shaper.compute_composite_reward(
            threat_mode=0,
            upstream_queues=upstream,
            downstream_queues=downstream,
            target_contained=False,
            distance_to_trap=150.0,
        )

        self.assertEqual(composite, r_traffic)
        self.assertEqual(r_traffic, -5.0)

    def test_security_override_mode(self):
        # When threat_mode m(t) == 1, reward must strictly equal r_security
        upstream = {"lane_0": 15.0}
        composite, r_traffic, r_security = self.shaper.compute_composite_reward(
            threat_mode=1,
            upstream_queues=upstream,
            target_contained=True,
            distance_to_trap=5.0,
        )

        self.assertEqual(composite, r_security)
        self.assertEqual(r_security, 100.0)

    def test_unauthorized_breakout_penalty(self):
        composite, r_traffic, r_security = self.shaper.compute_composite_reward(
            threat_mode=1,
            upstream_queues={},
            target_contained=False,
            unauthorized_breakout=True,
        )
        self.assertEqual(r_security, -200.0)
        self.assertEqual(composite, -200.0)

if __name__ == "__main__":
    unittest.main()
