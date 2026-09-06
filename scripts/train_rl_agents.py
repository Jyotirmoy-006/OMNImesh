"""
Omni-Mesh CLI Training Script
Spins up the Gymnasium SUMOTraCIEnvironment, builds the PPO training harness,
and executes the dual-objective policy training with periodic checkpointing.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omnimesh.utils.logger import logger
from omnimesh.simulation.traci_env import SUMOTraCIEnvironment
from omnimesh.tier1_edge.rl_trainer import OmniMeshRLTrainer

def main():
    parser = argparse.ArgumentParser(description="Omni-Mesh PPO Training Pipeline")
    parser.add_argument(
        "--timesteps",
        type=int,
        default=20000,
        help="Total environment timesteps to train",
    )
    parser.add_argument(
        "--save-freq",
        type=int,
        default=10000,
        help="Timestep interval for saving model checkpoints",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="models/checkpoints",
        help="Directory where model checkpoints will be saved",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Run post-training evaluation episodes",
    )
    args = parser.parse_args()

    logger.info("===========================================================")
    logger.info("OMNI-MESH: PHASE 2 DUAL-OBJECTIVE PPO TRAINING PIPELINE")
    logger.info("===========================================================")
    logger.info(f"Target Timesteps : {args.timesteps}")
    logger.info(f"Checkpoint Interval: Every {args.save_freq} steps")
    logger.info(f"Checkpoint Output  : {args.checkpoint_dir}")

    # Spin up the Gymnasium SUMO environment
    logger.info("Initializing Gymnasium SUMO TraCI Environment...")
    env = SUMOTraCIEnvironment(gui=False, step_length=1.0)

    try:
        # Initialize the PPO trainer
        trainer = OmniMeshRLTrainer(
            env=env,
            checkpoint_dir=args.checkpoint_dir,
            save_freq=args.save_freq,
        )

        # Start PPO training
        trainer.train(total_timesteps=args.timesteps)

        if args.eval:
            logger.info("Executing post-training evaluation...")
            trainer.evaluate(eval_episodes=3)

    finally:
        env.close()
        logger.info("SUMO TraCI environment closed cleanly.")

if __name__ == "__main__":
    main()
