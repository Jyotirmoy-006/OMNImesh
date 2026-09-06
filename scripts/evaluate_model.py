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
from omnimesh.simulation.scenario_generator import ScenarioGenerator

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

def build_approach_mapping(env: SUMOTraCIEnvironment) -> Tuple[Dict[str, Dict[str, List[str]]], List[str]]:
    """
    Builds directional approach mapping (East-West and North-South incoming edges)
    for all 16 traffic lights and compiles a flat list of all network approach edges.
    """
    import sumolib
    net_path = getattr(env, "net_file", "data/networks/grid_4x4.net.xml")
    net = sumolib.net.readNet(net_path)
    tls_map: Dict[str, Dict[str, List[str]]] = {}
    all_approaches: List[str] = []

    for node in net.getNodes():
        if node.getType() == "traffic_light":
            nid = node.getID()
            ew_edges, ns_edges = [], []
            for e in node.getIncoming():
                eid = e.getID()
                all_approaches.append(eid)
                shape = e.getShape()
                dx = abs(shape[-1][0] - shape[0][0])
                dy = abs(shape[-1][1] - shape[0][1])
                if dx >= dy:
                    ew_edges.append(eid)
                else:
                    ns_edges.append(eid)
            tls_map[nid] = {"ew": ew_edges, "ns": ns_edges}

    # Fallback if any tls missing
    for tls_id in env.tls_ids:
        if tls_id not in tls_map:
            tls_map[tls_id] = {"ew": [], "ns": []}

    all_approaches = list(set(all_approaches))
    return tls_map, all_approaches

def run_evaluation_episode(
    env: SUMOTraCIEnvironment,
    policy_type: str,
    tls_map: Dict[str, Dict[str, List[str]]],
    all_approach_edges: List[str],
    model: Any = None,
    max_steps: int = 50,
    seed: int = 100,
) -> Dict[str, Any]:
    """
    Executes a single deterministic evaluation episode with suspect containment injection.
    Extracts halting queue lengths across all approach edges via traci.edge.getLastStepHaltingNumber().
    Calculates containment by checking if suspect vehicle drops to 0.0 m/s inside node C2 bounding box
    while perimeter signals are red.
    """
    obs, info = env.reset(seed=seed)
    total_reward = 0.0
    queues_history = []
    speeds_history = []
    contained = False

    target_plate = "SUSPECT-892"
    suspect_injected = False

    # Immediate bounding box for containment trap node C2 (center at 380, 380)
    c2_bbox = {"x_min": 350.0, "x_max": 410.0, "y_min": 350.0, "y_max": 410.0}

    for step in range(max_steps):
        # 1. Inject suspect vehicle at step 2 with forced trajectory crossing C2
        if step == 2 and not suspect_injected:
            env.inject_suspect_vehicle(vehicle_id=target_plate, direct_approach=True)
            suspect_injected = True

        # 2. Activate threat mode flag m(t)=1 at step 5
        if step == 5:
            env.set_threat_flag(active=True)

        # 3. Policy Action Selection
        if policy_type == "PPO":
            action, _ = model.predict(obs, deterministic=True)
        elif policy_type == "Max-Pressure":
            # Mode 2 Max-Pressure baseline:
            # For each intersection, discharges the approach with higher halting pressure
            actions = []
            for tls_id in env.tls_ids:
                approaches = tls_map.get(tls_id, {"ew": [], "ns": []})
                q_ew = sum(env.conn.edge.getLastStepHaltingNumber(e) for e in approaches["ew"])
                q_ns = sum(env.conn.edge.getLastStepHaltingNumber(e) for e in approaches["ns"])
                # Phase 2 is EW Green, Phase 0 is NS Green
                actions.append(2 if q_ew >= q_ns else 0)
            action = np.array(actions, dtype=np.int32)
        else:
            action = np.zeros(len(env.tls_ids), dtype=np.int32)

        # 4. Step physics
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward

        # 5. Extract ground truth speeds
        gt_vehicles = info.get("ground_truth_vehicles", {})
        if gt_vehicles:
            speeds = [v["speed"] for v in gt_vehicles.values()]
            speeds_history.append(float(np.mean(speeds)))

        # 6. Extract halting queue length across all approach edges via traci.edge.getLastStepHaltingNumber()
        step_halting = sum(env.conn.edge.getLastStepHaltingNumber(edge) for edge in all_approach_edges)
        queues_history.append(float(step_halting))

        # 7. Check containment success:
        # Verify if suspect vehicle speed drops to 0.0 m/s inside C2 bounding box while perimeter signals are red
        if target_plate in gt_vehicles and not contained:
            pos = gt_vehicles[target_plate]["position"]
            speed = gt_vehicles[target_plate]["speed"]

            in_c2_box = (
                c2_bbox["x_min"] <= pos[0] <= c2_bbox["x_max"]
                and c2_bbox["y_min"] <= pos[1] <= c2_bbox["y_max"]
            )
            speed_zero = (speed <= 0.1)  # Stopped at stop line

            # Check if C2 perimeter signals show red
            c2_state = env.conn.trafficlight.getRedYellowGreenState("C2")
            perimeter_red = any(ch in ("r", "R") for ch in c2_state)

            if in_c2_box and speed_zero and perimeter_red:
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
    parser.add_argument("--episodes", type=int, default=10, help="Number of evaluation episodes per policy (default: 10)")
    parser.add_argument("--steps", type=int, default=50, help="Max simulation steps per episode (default: 50)")
    parser.add_argument("--model-path", type=str, default="", help="Path to PPO .zip model")
    args = parser.parse_args()

    model_path = args.model_path or find_latest_checkpoint()
    logger.info(f"Loading trained PPO model from: {model_path}")
    model = PPO.load(model_path)

    env = SUMOTraCIEnvironment(gui=False, step_length=1.0)
    tls_map, all_approach_edges = build_approach_mapping(env)

    logger.info("==================================================================")
    logger.info("STARTING DETERMINISTIC COMPARATIVE BENCHMARK: PPO vs MAX-PRESSURE")
    logger.info(f"Episodes: {args.episodes} | Steps per Episode: {args.steps}")
    logger.info(f"Tracked Approach Edges for Halting Queues: {len(all_approach_edges)}")
    logger.info("==================================================================")

    ppo_results = []
    mp_results = []

    try:
        # Evaluate PPO Policy (10 episodes)
        logger.info(f"[1/2] Evaluating Trained PPO Neural Network Policy ({args.episodes} episodes)...")
        for ep in range(args.episodes):
            res = run_evaluation_episode(
                env=env,
                policy_type="PPO",
                tls_map=tls_map,
                all_approach_edges=all_approach_edges,
                model=model,
                max_steps=args.steps,
                seed=100 + ep,
            )
            ppo_results.append(res)
            logger.info(
                f"  PPO Episode {ep+1:2d}/{args.episodes}: "
                f"Queue={res['avg_queue']:5.1f} veh | "
                f"Speed={res['avg_speed']:4.1f} m/s | "
                f"Reward={res['total_reward']:7.1f} | "
                f"Contained={res['contained']}"
            )

        # Evaluate Mode 2 Max-Pressure Policy (10 episodes)
        logger.info(f"[2/2] Evaluating Mode 2 Max-Pressure Fallback Policy ({args.episodes} episodes)...")
        for ep in range(args.episodes):
            res = run_evaluation_episode(
                env=env,
                policy_type="Max-Pressure",
                tls_map=tls_map,
                all_approach_edges=all_approach_edges,
                max_steps=args.steps,
                seed=100 + ep,
            )
            mp_results.append(res)
            logger.info(
                f"  MaxPressure Episode {ep+1:2d}/{args.episodes}: "
                f"Queue={res['avg_queue']:5.1f} veh | "
                f"Speed={res['avg_speed']:4.1f} m/s | "
                f"Reward={res['total_reward']:7.1f} | "
                f"Contained={res['contained']}"
            )

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

    queue_delta = ((mp_avg_queue - ppo_avg_queue) / max(1e-5, mp_avg_queue)) * 100.0

    table_data = [
        ["Policy Architecture", "Avg Queue (veh)", "Containment Success Rate", "Avg Speed (m/s)", "Mean Cumulative Reward"],
        ["Trained PPO Policy (MlpPolicy)", f"{ppo_avg_queue:.2f}", f"{ppo_contain_rate:.1f}%", f"{ppo_avg_speed:.2f}", f"{ppo_reward:.1f}"],
        ["Mode 2 Max-Pressure Fallback", f"{mp_avg_queue:.2f}", f"{mp_contain_rate:.1f}%", f"{mp_avg_speed:.2f}", f"{mp_reward:.1f}"],
        ["Relative Delta / Advantage", f"{queue_delta:+.1f}% Queue Delta", f"{ppo_contain_rate - mp_contain_rate:+.1f}% Containment Adv.", f"{(ppo_avg_speed - mp_avg_speed):+.2f} m/s", f"{(ppo_reward - mp_reward):+.1f}"],
    ]

    print("\n" + "=" * 80)
    print(f"           OMNI-MESH BENCHMARK EVALUATION RESULTS ({args.episodes} EPISODES)")
    print("================================================================================")

    if HAS_TABULATE:
        print(tabulate(table_data[1:], headers=table_data[0], tablefmt="grid"))
    else:
        for row in table_data:
            print(" | ".join(f"{str(cell):<26}" for cell in row))

    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
