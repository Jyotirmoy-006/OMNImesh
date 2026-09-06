class DecoupledPipelineManager:
    """
    Manages frequency-decoupled execution:
      - Thread A: Perception (15 FPS, NCNN INT8)
      - Thread B: ANPR (1-3 FPS, event-triggered)
      - Thread C: RL Control (1-2 Hz, <2% CPU)
      - Thread D: Network I/O (Async event-driven)
    """
    def __init__(self):
        self.is_running = False

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False
