from typing import Dict, List, Optional
import time

class WatchlistManager:
    """
    Maintains active license plate watchlists and suspect trajectory history.
    """
    def __init__(self):
        self.watchlist: Dict[str, Dict[str, str]] = {}
        self.sightings: List[Dict[str, str]] = []

    def add_to_watchlist(self, plate: str, description: str, priority: str = "HIGH"):
        self.watchlist[plate] = {
            "description": description,
            "priority": priority,
            "added_at": time.time(),
        }

    def is_flagged(self, plate: str) -> bool:
        return plate in self.watchlist

    def record_sighting(self, plate: str, node_id: str, timestamp: float, confidence: float):
        if self.is_flagged(plate):
            self.sightings.append({
                "plate": plate,
                "node_id": node_id,
                "timestamp": timestamp,
                "confidence": confidence,
            })
