"""
Omni-Mesh Scenario Generator
Spawns synthetic emergency vehicles and suspect watchlist vehicles into SUMO via TraCI,
forcing trajectories through designated containment trap nodes (Node C2).
"""

from typing import Optional, List, Any
import traci
from omnimesh.utils.logger import logger

class ScenarioGenerator:
    """
    Injects synthetic emergency vehicles and suspect watchlist vehicles into SUMO.
    Forces suspect vehicles through designated containment trap corridors (node C2).
    """

    # Predefined routes crossing designated containment trap node C2 (x=380, y=380)
    ROUTE_C2_APPROACH = ["B2C2", "C2D2", "D2right2"]
    ROUTE_C2_FULL_WE = ["left2A2", "A2B2", "B2C2", "C2D2", "D2right2"]
    ROUTE_C2_APPROACH_SN = ["C1C2", "C2C3", "C3top2"]
    ROUTE_C2_FULL_SN = ["bottom2C0", "C0C1", "C1C2", "C2C3", "C3top2"]

    DEFAULT_SUSPECT_TYPE = "suspect"
    DEFAULT_EMERGENCY_TYPE = "ambulance"
    DEFAULT_TARGET_PLATE = "SUSPECT-892"

    def __init__(self, traci_conn: Optional[Any] = None):
        self.conn = traci_conn

    def _get_conn(self) -> Any:
        return self.conn if self.conn is not None else traci

    def set_connection(self, traci_conn: Any):
        """Updates the active TraCI connection handle."""
        self.conn = traci_conn

    def register_route(self, route_id: str, edges: List[str]) -> bool:
        """Registers a predefined route in SUMO if not already existing."""
        conn = self._get_conn()
        try:
            conn.route.add(route_id, edges)
            return True
        except Exception:
            # Route may already exist
            return False

    def inject_watchlist_suspect(
        self,
        vehicle_id: str = DEFAULT_TARGET_PLATE,
        entry_edge: Optional[str] = None,
        direct_approach: bool = True,
        vtype: str = DEFAULT_SUSPECT_TYPE,
    ) -> bool:
        """
        Injects a watchlist suspect vehicle into SUMO with a forced trajectory crossing
        containment trap node C2.
        
        Args:
            vehicle_id: Plate ID (default: "SUSPECT-892")
            entry_edge: Optional entry edge. If "B2C2" or None with direct_approach=True,
                        routes directly from B2C2 across C2 to ensure immediate containment evaluation.
            direct_approach: If True, uses ROUTE_C2_APPROACH ("B2C2" -> "C2D2" -> "D2right2").
                             If False, uses full corridor ROUTE_C2_FULL_WE.
            vtype: Vehicle type in SUMO matching watchlist parameters ("suspect").
        """
        conn = self._get_conn()
        try:
            if direct_approach or entry_edge == "B2C2":
                route_edges = self.ROUTE_C2_APPROACH
                route_id = f"route_c2_approach_{vehicle_id}"
            else:
                route_edges = self.ROUTE_C2_FULL_WE
                route_id = f"route_c2_full_{vehicle_id}"

            self.register_route(route_id, route_edges)

            conn.vehicle.add(
                vehID=vehicle_id,
                routeID=route_id,
                typeID=vtype,
                depart="now",
                departLane="best",
                departSpeed="max",
            )
            # High-visibility amber color for suspect
            conn.vehicle.setColor(vehicle_id, (245, 158, 11, 255))
            logger.warning(
                f"[ScenarioGenerator] Injected Watchlist Suspect [{vehicle_id}] (type={vtype}) "
                f"routed through C2 on edges: {' -> '.join(route_edges)}"
            )
            return True
        except Exception as e:
            logger.error(f"[ScenarioGenerator] Failed to inject suspect vehicle [{vehicle_id}]: {e}")
            return False

    def inject_emergency_vehicle(
        self,
        vehicle_id: str = "AMB_01",
        corridor_row: int = 1,
        vtype: str = DEFAULT_EMERGENCY_TYPE,
    ) -> bool:
        """Injects a high-priority emergency vehicle along a specified corridor."""
        conn = self._get_conn()
        try:
            route_id = f"route_amb_{vehicle_id}"
            from_edge = f"left{corridor_row}A{corridor_row}"
            mid1 = f"A{corridor_row}B{corridor_row}"
            mid2 = f"B{corridor_row}C{corridor_row}"
            mid3 = f"C{corridor_row}D{corridor_row}"
            to_edge = f"D{corridor_row}right{corridor_row}"
            route_edges = [from_edge, mid1, mid2, mid3, to_edge]

            self.register_route(route_id, route_edges)

            conn.vehicle.add(
                vehID=vehicle_id,
                routeID=route_id,
                typeID=vtype,
                depart="now",
                departLane="best",
                departSpeed="max",
            )
            conn.vehicle.setColor(vehicle_id, (255, 30, 30, 255))
            logger.warning(
                f"[ScenarioGenerator] Injected Emergency Vehicle [{vehicle_id}] on corridor {corridor_row}"
            )
            return True
        except Exception as e:
            logger.error(f"[ScenarioGenerator] Failed to inject emergency vehicle: {e}")
            return False
