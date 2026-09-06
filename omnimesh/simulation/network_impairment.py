class NetworkImpairmentSimulator:
    """
    Simulates real-world IoT impairments: latency injection, packet drop,
    and sudden broker process crashes for ZSPF stress testing.
    """
    def __init__(self, drop_probability: float = 0.05, latency_ms: float = 10.0):
        self.drop_probability = drop_probability
        self.latency_ms = latency_ms
