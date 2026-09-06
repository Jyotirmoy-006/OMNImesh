import unittest
import numpy as np
from omnimesh.simulation.mock_perception import MockPerception
from omnimesh.simulation.traci_env import SUMOTraCIEnvironment

class TestSUMOPerception(unittest.TestCase):
    def test_mock_perception_gaussian_noise(self):
        perception = MockPerception(mean_accuracy=0.98, std_accuracy=0.03)
        gt_vehicles = {
            "veh_0": {"position": (100.0, 100.0), "speed": 12.0, "lane_id": "lane_0", "type": "car"},
            "veh_1": {"position": (250.0, 250.0), "speed": 10.0, "lane_id": "lane_1", "type": "car"},
        }
        intersections = {
            "node_0_0": {"x": 80.0, "y": 80.0, "row": 0, "col": 0},
        }

        result = perception.process_ground_truth(gt_vehicles, intersections)
        self.assertIn("detected_vehicles", result)
        self.assertFalse(result["thermal_throttled"])

    def test_mock_perception_thermal_dropout(self):
        perception = MockPerception()
        perception.set_thermal_state(temp_c=85.0, throttled=True)
        self.assertTrue(perception.thermal_throttle)

        # Generate 100 dummy vehicles to verify dropout
        gt_vehicles = {
            f"veh_{i}": {"position": (100.0 + i, 100.0), "speed": 10.0, "lane_id": "l", "type": "car"}
            for i in range(100)
        }
        intersections = {"node_0": {"x": 100.0, "y": 100.0}}
        result = perception.process_ground_truth(gt_vehicles, intersections)
        self.assertTrue(result["thermal_throttled"])
        # With 40% dropout rate, dropped count should be > 10
        self.assertGreater(result["dropped_count"], 10)

if __name__ == "__main__":
    unittest.main()
