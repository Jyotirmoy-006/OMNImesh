import argparse
import sys
import time
from pathlib import Path

# Add project root to path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omnimesh.utils.logger import logger
from omnimesh.simulation.traci_env import SUMOTraCIEnvironment
from omnimesh.simulation.scenario_generator import ScenarioGenerator
from omnimesh.tier1_edge.agent import EdgeNodeAgent
from omnimesh.tier2_orchestrator.orchestrator import GlobalZoneOrchestrator

def main():
    parser = argparse.ArgumentParser(description="Omni-Mesh Co-Simulation Runner")
    parser.add_argument("--config", type=str, default="configs/simulation_config.yaml", help="Path to config file")
    args = parser.parse_args()

    logger.info("Initializing Omni-Mesh Simulation Harness...")
    env = SUMOTraCIEnvironment(network_file="data/networks/grid.net.xml", route_file="data/networks/grid.rou.xml")
    orchestrator = GlobalZoneOrchestrator(zone_id="zone_alpha")
    agent = EdgeNodeAgent(node_id="node_1_1", incoming_lanes=["lane_0", "lane_1", "lane_2", "lane_3"])
    scenario = ScenarioGenerator()

    env.start()
    scenario.inject_emergency_vehicle("AMB_01", "edge_0_0", "edge_3_3")

    logger.info("Running simulation step loop (Demo)...")
    for step in range(10):
        t = time.time()
        action = agent.step(current_time=t)
        env.step()
        logger.info(f"Step {step}: Agent action selected -> Phase {action}")

    env.close()
    logger.info("Simulation completed successfully.")

if __name__ == "__main__":
    main()
