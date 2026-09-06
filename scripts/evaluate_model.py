"""
Omni-Mesh Model Evaluation Script
Executes deterministic comparative benchmark episodes comparing the trained
PPO Neural Network policy against the Mode 2 Max-Pressure fallback.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omnimesh.utils.logger import logger
from omnimesh.simulation.traci_env import SUMOTraCIEnvironment

try:
    from stable_baselines3 import PPO
    HAS_PPO = True
except ImportError:
    HAS_PPO = False

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

def find_latest_checkpoint(checkpoint_dir: str = "models/checkpoints") -> str:
    p = Path(checkpoint_dir)
    final_model = p / "omnimesh_ppo_final.zip"
    if final_model.exists():
        return str(final_model)
    checkpoints = list(p.glob("*.zip"))
    if not checkpoints:
        raise FileNotFoundError(f"No .zip model checkpoints found in {checkpoint_dir}")
    latest = max(checkpoints, key=lambda f: f.stat().st_mtime)
    return str(latest)

def run_evaluation_episode(
    env: SUMOTraCIEnvironment,
    policy_type: str,
    model: Any = None,
    max_steps: int = 100,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Executes a single deterministic evaluation episode with suspect containment injection.
    """
    obs, info = env.reset(seed=seed)
    total_reward = 0.0
    queues_history = []
    speeds_history = []
    contained = False

    target_plate = "SUSPECT-892"
    suspect_injected = False

    for step in range(max_steps):
        # Inject suspect vehicle at step 15
        if step == 15 and not suspect_injected:
            env.inject_suspect_vehicle(vehicle_id=target_plate, corridor_row=2)
            suspect_injected = True

        # Activate threat mode flag m(t)=1 at step 25
        if step == 25:
            env.set_threat_flag(active=True)

        # Policy Action Selection
        if policy_type == "PPO":
            action, _ = model.predict(obs, deterministic=True)
        elif policy_type == "Max-Pressure":
            # Mode 2 Max-Pressure deterministic policy:
            # Pick phase that discharges the largest approach queue
            actions = []
            for i in range(len(env.tls_ids)):
                idx = i * env.features_per_node
                q_ew = obs[idx + 0]
                q_ns = obs[idx + 1]
                actions.append(0 if q_ew >= q_ns else 1)
            action = np.array(actions, dtype=np.int32)
        else:
            action = np.zeros(len(env.tls_ids), dtype=np.int32)

        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward

        gt_vehicles = info.get("ground_truth_vehicles", {})
        if gt_vehicles:
            speeds = [v["speed"] for v in gt_vehicles.values()]
            speeds_history.append(np.mean(speeds))

        # Measure network-wide queue length from observation
        step_queues = [obs[i * env.features_per_node] + obs[i * env.features_per_node + 1] for i in range(len(env.tls_ids))]
        queues_history.append(np.sum(step_queues))

        # Check containment success
        if target_plate in gt_vehicles:
            pos = gt_vehicles[target_plate]["position"]
            speed = gt_vehicles[target_plate]["speed"]
            # Trap intersection C2 is at (380, 380)
            dist_to_c2 = np.hypot(pos[0] - 380.0, pos[1] - 380.0)
            if dist_to_c2 < 30.0 and speed < 1.0:
                contained = True

        if terminated or truncated:
            break

    avg_queue = float(np.mean(queues_history)) if queues_history else 0.0
    avg_speed = float(np.mean(speeds_history)) if speeds_history else 0.0

    return {
        "avg_queue": avg_queue,
        "avg_speed": avg_speed,
        "total_reward": total_reward,
        "contained": contained,
    }

def main():
    parser = argparse.ArgumentParser(description="Omni-Mesh PPO vs Max-Pressure Benchmark Evaluation")
    parser.add_argument("--episodes", type=int, default=5, help="Number of evaluation episodes per policy")
    parser.add_argument("--steps", type=int, default=100, help="Max simulation steps per episode")
    parser.add_argument("--model-path", type=str, default="", help="Path to PPO .zip model")
    args = parser.parse_args()

    model_path = args.model_path or find_latest_checkpoint()
    logger.info(f"Loading trained PPO model from: {model_path}")
    model = PPO.load(model_path)

    env = SUMOTraCIEnvironment(gui=False, step_length=1.0)

    logger.info("==================================================================")
    logger.info("STARTING DETERMINISTIC COMPARATIVE BENCHMARK: PPO vs MAX-PRESSURE")
    logger.info(f"Episodes: {args.episodes} | Steps per Episode: {args.steps}")
    logger.info("==================================================================")

    ppo_results = []
    mp_results = []

    try:
        # Evaluate PPO Policy
        logger.info("[1/2] Evaluating Trained PPO Neural Network Policy...")
        for ep in range(args.episodes):
            res = run_evaluation_episode(env, policy_type="PPO", model=model, max_steps=args.steps, seed=100 + ep)
            ppo_results.append(res)
            logger.info(f"  PPO Episode {ep+1}: Queue={res['avg_queue']:.1f}, Reward={res['total_reward']:.1f}, Contained={res['contained']}")

        # Evaluate Mode 2 Max-Pressure Policy
        logger.info("[2/2] Evaluating Mode 2 Max-Pressure Fallback Policy...")
        for ep in range(args.episodes):
            res = run_evaluation_episode(env, policy_type="Max-Pressure", max_steps=args.steps, seed=100 + ep)
            mp_results.append(res)
            logger.info(f"  MaxPressure Episode {ep+1}: Queue={res['avg_queue']:.1f}, Reward={res['total_reward']:.1f}, Contained={res['contained']}")

    finally:
        env.close()

    # Aggregate metrics
    ppo_avg_queue = float(np.mean([r["avg_queue"] for r in ppo_results]))
    ppo_contain_rate = float(np.mean([100.0 if r["contained"] else 0.0 for r in ppo_results]))
    ppo_avg_speed = float(np.mean([r["avg_speed"] for r in ppo_results]))
    ppo_reward = float(np.mean([r["total_reward"] for r in ppo_results]))

    mp_avg_queue = float(np.mean([r["avg_queue"] for r in mp_results]))
    mp_contain_rate = float(np.mean([100.0 if r["contained"] else 0.0 for r in mp_results]))
    mp_avg_speed = float(np.mean([r["avg_speed"] for r in mp_results]))
    mp_reward = float(np.mean([r["total_reward"] for r in mp_results]))

    queue_improvement = ((mp_avg_queue - ppo_avg_queue) / max(1e-5, mp_avg_queue)) * 100.0

    table_data = [
        ["Policy Architecture", "Avg Queue (veh)", "Containment Success Rate", "Avg Speed (m/s)", "Mean Cumulative Reward"],
        ["Trained PPO Policy (MlpPolicy)", f"{ppo_avg_queue:.2f}", f"{ppo_contain_rate:.1f}%", f"{ppo_avg_speed:.2f}", f"{ppo_reward:.1f}"],
        ["Mode 2 Max-Pressure Fallback", f"{mp_avg_queue:.2f}", f"{mp_contain_rate:.1f}%", f"{mp_avg_speed:.2f}", f"{mp_reward:.1f}"],
        ["Relative Delta / Advantage", f"{queue_improvement:+.1f}% Queue Reduction", f"{ppo_contain_rate - mp_contain_rate:+.1f}% Delta", f"{(ppo_avg_speed - mp_avg_speed):+.2f} m/s", f"{(ppo_reward - mp_reward):+.1f}"],
    ]

    print("\n" + "=" * 80)
    print("           OMNI-MESH BENCHMARK EVALUATION RESULTS (5 EPISODES)")
    print("=" * 80)

    if HAS_TABULATE:
        print(tabulate(table_data[1:], headers=table_data[0], tablefmt="grid"))
    else:
        for row in table_data:
            print(" | ".join(f"{str(cell):<26}" for cell in row))

    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
