from typing import Dict, List

class MetricsCollector:
    """
    Records traffic flow, queue lengths, latency, and recovery time metrics.
    """
    def __init__(self):
        self.history: List[Dict[str, float]] = []

    def record_step(self, step: int, avg_wait: float, throughput: float):
        self.history.append({
            "step": step,
            "avg_wait": avg_wait,
            "throughput": throughput,
        })
