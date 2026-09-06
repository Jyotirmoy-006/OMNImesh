"""
Omni-Mesh Vision Detector & Mock Perception IPC Worker
Runs isolated MockPerception in its own OS-level process (Process A) at 15 Hz,
pushing mocked TraCI queue states to a multiprocessing.Queue and dropping the
oldest frames if full to prevent IPC memory bloat.
"""

import time
import queue
from queue import Empty, Full
import multiprocessing
from typing import List, Dict, Any, Optional
import numpy as np
from omnimesh.utils.logger import logger

def push_to_ipc_queue(ipc_queue: multiprocessing.Queue, item: Any) -> bool:
    """
    Pushes an item to the IPC queue.
    If the queue is full, drops the oldest frame before inserting the new one,
    strictly preventing IPC memory bloat and queue buildup.
    """
    try:
        ipc_queue.put_nowait(item)
        return True
    except (Full, queue.Full):
        try:
            # Drop the oldest frame
            _ = ipc_queue.get_nowait()
        except (Empty, queue.Empty):
            pass

        try:
            ipc_queue.put_nowait(item)
            return True
        except (Full, queue.Full):
            return False

def run_detector_process(
    ipc_queue: multiprocessing.Queue,
    stop_event: multiprocessing.Event,
    frequency_hz: float = 15.0,
    nodes: Optional[List[str]] = None,
):
    """
    Target function for isolated perception multiprocessing.Process (Process A).
    Continuously samples and generates mocked TraCI queue state at 15 Hz,
    pushing updates into the IPC Queue for Tier-1 Edge Agents.
    """
    period = 1.0 / max(1.0, frequency_hz)
    frame_id = 0
    node_list = nodes or [f"node_{r}_{c}" for r in range(4) for c in range(4)]

    logger.info(
        f"[Process A: Detector] Started MockPerception loop at {frequency_hz:.1f} Hz "
        f"for {len(node_list)} intersections."
    )

    while not stop_event.is_set():
        loop_start = time.time()

        # Build mocked TraCI queue state representing high-frequency perception observations
        node_queues: Dict[str, Dict[str, Any]] = {}
        for node_id in node_list:
            # Dynamic queue densities per approach with realistic traffic distribution
            base_ew = float(np.random.poisson(3.0))
            base_ns = float(np.random.poisson(2.5))
            node_queues[node_id] = {
                "EW": base_ew,
                "NS": base_ns,
                "queues": {
                    "east": base_ew / 2.0,
                    "west": base_ew / 2.0,
                    "north": base_ns / 2.0,
                    "south": base_ns / 2.0,
                },
                "confidence": float(np.clip(np.random.normal(0.98, 0.03), 0.70, 1.0)),
            }

        payload: Dict[str, Any] = {
            "frame_id": frame_id,
            "timestamp": loop_start,
            "source": "ProcessA_MockPerception",
            "frequency_hz": frequency_hz,
            "node_queues": node_queues,
        }

        # Push to IPC Queue with oldest-frame eviction on full
        push_to_ipc_queue(ipc_queue, payload)
        frame_id += 1

        elapsed = time.time() - loop_start
        sleep_time = max(0.0, period - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    logger.info("[Process A: Detector] Perception process received stop signal. Terminating loop.")

class VehicleDetector:
    """
    Lightweight vehicle & emergency vehicle detector using YOLOv8n NCNN INT8 format.
    Runs in Thread/Process A at 15 FPS.
    """
    def __init__(self, model_format: str = "ncnn_int8"):
        self.model_format = model_format

    def detect_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        # In actual HiL deployment, runs ncnn/onnx forward pass
        # Simulated return: bounding boxes, class names, and tracking IDs
        return [
            {"bbox": [100, 150, 200, 250], "class": "car", "confidence": 0.94, "track_id": 101},
        ]
