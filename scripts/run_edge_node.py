import argparse
import sys
import time
from pathlib import Path

# Add project root to path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omnimesh.utils.logger import logger
from omnimesh.tier1_edge.agent import EdgeNodeAgent

def main():
    parser = argparse.ArgumentParser(description="Omni-Mesh Physical/Virtual Edge Node")
    parser.add_argument("--node-id", type=str, default="node_01", help="Unique Intersection Node ID")
    args = parser.parse_args()

    logger.info(f"Starting Omni-Mesh Edge Node [{args.node_id}]...")
    agent = EdgeNodeAgent(node_id=args.node_id, incoming_lanes=["north", "south", "east", "west"])

    logger.info("Edge Node operational. Running decoupled agent loop.")

if __name__ == "__main__":
    main()
