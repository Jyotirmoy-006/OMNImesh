class BrokerTopologyManager:
    """
    Manages dual-level broker architecture: Local Zone Broker (edge subnet)
    and Global Broker (Tier-2 orchestrator).
    """
    def __init__(self, zone_broker_url: str, global_broker_url: str):
        self.zone_broker_url = zone_broker_url
        self.global_broker_url = global_broker_url
