"""
Unit & Integration Tests for Decoupled Multiprocessing Vision Pipeline
Tests:
  1. Multiprocessing Process spawning with daemon=True
  2. 15 Hz MockPerception IPC Queue push with oldest-frame eviction on full
  3. Non-blocking get_nowait() reads in EdgeNodeAgent with clean queue.Empty fallback
"""

import unittest
import time
import queue
from queue import Empty
import multiprocessing
import numpy as np

from omnimesh.vision.detector import push_to_ipc_queue, VehicleDetector
from omnimesh.vision.pipeline_manager import DecoupledPipelineManager
from omnimesh.tier1_edge.agent import EdgeNodeAgent

class TestDecoupledVisionPipeline(unittest.TestCase):
    def test_ipc_queue_drop_oldest_frame_when_full(self):
        """
        Verifies Constraint 2:
        If the queue is full, push_to_ipc_queue drops the oldest frame to prevent IPC memory bloat.
        """
        q = multiprocessing.Queue(maxsize=3)

        # Fill the queue to capacity
        self.assertTrue(push_to_ipc_queue(q, {"frame_id": 0}))
        self.assertTrue(push_to_ipc_queue(q, {"frame_id": 1}))
        self.assertTrue(push_to_ipc_queue(q, {"frame_id": 2}))

        # Queue is now full. Pushing frame 3 must drop frame 0 and insert frame 3
        success = push_to_ipc_queue(q, {"frame_id": 3})
        self.assertTrue(success)

        # Allow multiprocessing.Queue background feeder thread to transfer to pipe
        time.sleep(0.05)

        # Retrieve items: frame 0 must have been dropped, leaving 1, 2, 3
        f1 = q.get(timeout=1.0)
        f2 = q.get(timeout=1.0)
        f3 = q.get(timeout=1.0)

        self.assertEqual(f1["frame_id"], 1)
        self.assertEqual(f2["frame_id"], 2)
        self.assertEqual(f3["frame_id"], 3)

    def test_agent_non_blocking_read_and_empty_fallback(self):
        """
        Verifies Constraint 3:
        EdgeNodeAgent fetches state via get_nowait(), cleanly handles queue.Empty,
        and falls back to last known state when perception lags.
        """
        agent = EdgeNodeAgent(
            node_id="node_0_0",
            incoming_lanes=["north", "south", "east", "west"],
        )
        q = multiprocessing.Queue(maxsize=5)
        agent.set_ipc_queue(q)

        # 1. Test clean fallback on completely empty queue
        initial_state = agent.last_known_state.copy()
        action = agent.step(current_time=time.time())
        self.assertIn(action, [0, 1, 2, 3])
        # State should safely fall back to initial state
        np.testing.assert_array_almost_equal(agent.last_known_state, initial_state)

        # 2. Push perception update into IPC queue
        test_payload = {
            "frame_id": 42,
            "timestamp": time.time(),
            "node_queues": {
                "node_0_0": {
                    "EW": 10.0,
                    "NS": 2.0,
                    "queues": {
                        "east": 5.0,
                        "west": 5.0,
                        "north": 1.0,
                        "south": 1.0,
                    }
                }
            }
        }
        push_to_ipc_queue(q, test_payload)

        # 3. Agent steps, reads non-blocking, and updates state
        action_updated = agent.step(current_time=time.time())
        self.assertIn(action_updated, [0, 1, 2, 3])
        self.assertEqual(agent.last_perception_timestamp, test_payload["timestamp"])

        # 4. Step again immediately (queue now empty): must not crash, smoothly retains state
        action_fallback = agent.step(current_time=time.time() + 0.1)
        self.assertIn(action_fallback, [0, 1, 2, 3])

    def test_pipeline_manager_daemon_lifecycle(self):
        """
        Verifies Constraint 1:
        pipeline_manager MUST spawn multiprocessing.Process with daemon=True
        and streams high-frequency frames over IPC.
        """
        manager = DecoupledPipelineManager(
            queue_maxsize=15,
            frequency_hz=25.0,  # Fast test frequency
            nodes=["node_0_0", "node_0_1"],
        )
        try:
            manager.start()
            self.assertTrue(manager.is_alive())
            # Enforce Constraint 1: daemon=True
            self.assertTrue(manager.perception_process.daemon)

            # Wait for frames to be populated in IPC queue
            received_frames = []
            start_wait = time.time()
            while len(received_frames) < 3 and time.time() - start_wait < 3.0:
                try:
                    frame = manager.get_queue().get(timeout=0.5)
                    received_frames.append(frame)
                except Empty:
                    pass

            self.assertGreaterEqual(len(received_frames), 3)
            first_frame = received_frames[0]
            self.assertIn("node_queues", first_frame)
            self.assertIn("node_0_0", first_frame["node_queues"])
            self.assertEqual(first_frame["source"], "ProcessA_MockPerception")
        finally:
            manager.stop(timeout=2.0)
            self.assertFalse(manager.is_alive())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
