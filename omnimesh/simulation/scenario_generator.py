from omnimesh.utils.logger import logger

class ScenarioGenerator:
    """
    Injects synthetic emergency vehicles and suspect watchlist vehicles into SUMO.
    """
    def __init__(self):
        pass

    def inject_emergency_vehicle(self, vehicle_id: str, origin: str, destination: str):
        logger.info(f"Injecting Emergency Vehicle [{vehicle_id}] from {origin} to {destination}")

    def inject_watchlist_suspect(self, plate: str, entry_edge: str):
        logger.info(f"Injecting Watchlist Suspect vehicle [{plate}] at edge {entry_edge}")
