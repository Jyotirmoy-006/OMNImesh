"""
Decoupled Vision & Perception Pipeline Manager
Spawns OS-level multiprocessing.Process with daemon=True to decouple the high-frequency
MockPerception loop (Process A, 15 Hz) from the low-frequency RL Control loop (Process C, 1-2 Hz).
"""

import multiprocessing
from typing import Optional, List, Dict, Any
from omnimesh.utils.logger import logger
from .detector import run_detector_process, VehicleDetector

class DecoupledPipelineManager:
    """
    Manages frequency-decoupled execution across OS process boundaries:
      - Process A: MockPerception / Vision Detector (15 Hz, isolated process space)
      - Process C / Main: RL Control loop (1-2 Hz) reading from IPC Queue

    Guarantees that Python GIL contention between high-frequency perception sampling
    and neural RL inference is strictly eliminated.
    """
    def __init__(
        self,
        queue_maxsize: int = 15,
        frequency_hz: float = 15.0,
        nodes: Optional[List[str]] = None,
    ):
        self.queue_maxsize = queue_maxsize
        self.frequency_hz = frequency_hz
        self.nodes = nodes

        # Inter-Process Communication (IPC) queue and shutdown event
        self.ipc_queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=queue_maxsize)
        self.stop_event: multiprocessing.Event = multiprocessing.Event()
        self.perception_process: Optional[multiprocessing.Process] = None
        self.is_running: bool = False

    def start(self):
        """
        Spawns the perception process with daemon=True.
        Enforces daemon=True so the worker cleanly terminates when the parent process exits.
        """
        if self.is_running and self.perception_process and self.perception_process.is_alive():
            logger.warning("[DecoupledPipelineManager] Perception process is already active.")
            return

        self.stop_event.clear()
        self.perception_process = multiprocessing.Process(
            target=run_detector_process,
            args=(self.ipc_queue, self.stop_event, self.frequency_hz, self.nodes),
            name="OmniMesh-Perception-ProcessA",
            daemon=True,  # Constraint 1: MUST spawn with daemon=True
        )
        self.perception_process.start()
        self.is_running = True
        logger.info(
            f"[DecoupledPipelineManager] Spawned Process A (PID: {self.perception_process.pid}, "
            f"daemon=True, freq={self.frequency_hz} Hz, queue_maxsize={self.queue_maxsize})."
        )

    def stop(self, timeout: float = 2.0):
        """Signals shutdown and joins the perception process cleanly."""
        if not self.is_running:
            return

        logger.info("[DecoupledPipelineManager] Signaling perception process to terminate...")
        self.stop_event.set()

        if self.perception_process and self.perception_process.is_alive():
            self.perception_process.join(timeout=timeout)
            if self.perception_process.is_alive():
                logger.warning(
                    "[DecoupledPipelineManager] Process A did not exit within timeout; terminating."
                )
                self.perception_process.terminate()
                self.perception_process.join(timeout=1.0)

        self.is_running = False
        logger.info("[DecoupledPipelineManager] Perception process terminated cleanly.")

    def get_queue(self) -> multiprocessing.Queue:
        """Returns the IPC queue for consumer processes/agents."""
        return self.ipc_queue

    def is_alive(self) -> bool:
        """Checks if the child perception process is currently running."""
        return bool(self.perception_process and self.perception_process.is_alive())
