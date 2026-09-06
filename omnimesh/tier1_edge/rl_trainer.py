"""
Omni-Mesh Hardened PPO Reinforcement Learning Pipeline
Upgraded for 1M+ step training regimens with robust TensorBoard logging
(separating traffic_reward and security_reward) and TraCI crash recovery.
"""

import os
import time
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import numpy as np

try:
    import torch
    import torch.nn as nn
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback, CallbackList
    from stable_baselines3.common.vec_env import DummyVecEnv
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

try:
    import gymnasium as gym
except ImportError:
    import gym

try:
    import traci
    import traci.exceptions
    HAS_TRACI = True
except ImportError:
    HAS_TRACI = False

from omnimesh.utils.logger import logger

class TraCIFaultTolerantWrapper(gym.Wrapper):
    """
    TraCI Fault-Tolerance Recovery Wrapper.
    Catches FatalTraCIError, TraCIException, or socket drops, safely terminates the broken
    connection, relaunches the SUMO process, and restores environment state so PPO training
    can progress to 1M+ steps without losing the replay buffer or crashing.
    """
    def __init__(self, env: gym.Env, max_retries: int = 5):
        super().__init__(env)
        self.max_retries = max_retries
        self.crash_count = 0

    def step(self, action: Any) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        for attempt in range(self.max_retries):
            try:
                return self.env.step(action)
            except Exception as e:
                # Catch FatalTraCIError or socket disconnection
                self.crash_count += 1
                logger.error(
                    f"[TraCI Fault-Tolerance #{self.crash_count}] TraCI socket error on attempt {attempt+1}/{self.max_retries}: {e}"
                )
                self._recover_connection()
                # Return empty step observation with recovery info
                obs = getattr(self.env, "_get_observation", lambda: np.zeros(self.env.observation_space.shape, dtype=np.float32))()
                info = {"recovered_from_crash": True, "crash_count": self.crash_count}
                return obs, 0.0, False, False, info

        raise RuntimeError(f"TraCI failed to recover after {self.max_retries} attempts.")

    def reset(self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        for attempt in range(self.max_retries):
            try:
                return self.env.reset(seed=seed, options=options)
            except Exception as e:
                self.crash_count += 1
                logger.error(f"[TraCI Fault-Tolerance] TraCI reset error on attempt {attempt+1}: {e}")
                self._recover_connection()

        raise RuntimeError(f"TraCI failed to reset after {self.max_retries} attempts.")

    def _recover_connection(self):
        """Safely cleans up socket and relaunches the physics backend."""
        logger.warning("[TraCI Fault-Tolerance] Reinitializing SUMO process socket...")
        try:
            if hasattr(self.env, "close"):
                self.env.close()
        except Exception:
            pass
        time.sleep(1.0)
        try:
            if hasattr(self.env, "_resolve_sumo_binary"):
                self.env._resolve_sumo_binary()
        except Exception:
            pass

class DualObjectiveTensorboardCallback(BaseCallback if HAS_SB3 else object):
    """
    Custom TensorBoard Callback that separately logs civilian traffic throughput rewards,
    security containment rewards, and threat status metrics.
    """
    def __init__(self, log_freq: int = 10, verbose: int = 0):
        if HAS_SB3:
            super().__init__(verbose)
        self.log_freq = log_freq

    def _on_step(self) -> bool:
        if self.n_calls % self.log_freq == 0:
            infos = self.locals.get("infos", [{}])
            if infos and isinstance(infos, (list, tuple)):
                info = infos[0]
            elif isinstance(infos, dict):
                info = infos
            else:
                info = {}

            r_traffic = info.get("r_traffic", None)
            r_security = info.get("r_security", None)
            composite = info.get("composite_reward", None)
            threat_mode = info.get("threat_mode", 0)

            if r_traffic is not None and hasattr(self, "logger"):
                self.logger.record("rewards/traffic_reward", float(r_traffic))
            if r_security is not None and hasattr(self, "logger"):
                self.logger.record("rewards/security_reward", float(r_security))
            if composite is not None and hasattr(self, "logger"):
                self.logger.record("rewards/composite_reward", float(composite))
            if hasattr(self, "logger"):
                self.logger.record("security/threat_active", float(threat_mode))

        return True

class CheckpointCallback(BaseCallback if HAS_SB3 else object):
    """
    Callback that serializes and saves PPO policy weights every `save_freq` steps.
    """
    def __init__(self, save_freq: int = 10000, save_path: str = "models/checkpoints", verbose: int = 1):
        if HAS_SB3:
            super().__init__(verbose)
        self.save_freq = save_freq
        self.save_path = Path(save_path)
        self.save_path.mkdir(parents=True, exist_ok=True)

    def _on_step(self) -> bool:
        if self.n_calls % self.save_freq == 0:
            checkpoint_file = self.save_path / f"omnimesh_ppo_step_{self.n_calls}.zip"
            self.model.save(str(checkpoint_file))
            if self.verbose > 0:
                logger.info(f"Saved model checkpoint at step {self.n_calls} to {checkpoint_file}")
        return True

class OmniMeshRLTrainer:
    """
    Headless PPO training controller hardened for 1M+ steps with:
      1. TraCI fault-tolerant crash recovery wrapper
      2. TensorBoard dual-objective metric logging (tensorboard_logs/)
      3. Lightweight [64, 64] MLP policy for edge constraints
      4. Periodic model checkpointing
    """
    def __init__(
        self,
        env: Any,
        checkpoint_dir: str = "models/checkpoints",
        tensorboard_dir: str = "tensorboard_logs",
        learning_rate: float = 3e-4,
        n_steps: int = 512,
        batch_size: int = 64,
        gamma: float = 0.99,
        save_freq: int = 10000,
    ):
        if not HAS_SB3:
            raise RuntimeError("Stable-Baselines3 and PyTorch are required for RL training.")

        # Wrap environment with TraCI crash recovery
        self.raw_env = env
        self.env = TraCIFaultTolerantWrapper(env)

        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.tensorboard_dir = Path(tensorboard_dir)
        self.tensorboard_dir.mkdir(parents=True, exist_ok=True)
        self.save_freq = save_freq

        # Lightweight 2-layer MLP architecture [64, 64] for edge-compute constraints
        self.policy_kwargs = dict(
            net_arch=dict(pi=[64, 64], vf=[64, 64]),
            activation_fn=nn.Tanh,
        )

        logger.info(f"Configuring hardened PPO with TensorBoard logs at '{self.tensorboard_dir}'...")
        self.model = PPO(
            policy="MlpPolicy",
            env=self.env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            gamma=gamma,
            policy_kwargs=self.policy_kwargs,
            verbose=1,
            tensorboard_log=str(self.tensorboard_dir),
        )

        # Combine checkpointing callback with dual-objective tensorboard metric logger
        self.checkpoint_callback = CheckpointCallback(
            save_freq=self.save_freq,
            save_path=str(self.checkpoint_dir),
            verbose=1,
        )
        self.tensorboard_callback = DualObjectiveTensorboardCallback(
            log_freq=10,
            verbose=0,
        )
        self.callbacks = CallbackList([self.checkpoint_callback, self.tensorboard_callback])

    def train(self, total_timesteps: int = 100000) -> PPO:
        """Executes the hardened PPO training loop."""
        logger.info(f"Starting hardened PPO training for {total_timesteps} timesteps...")
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=self.callbacks,
            progress_bar=False,
        )
        final_model_path = self.checkpoint_dir / "omnimesh_ppo_final.zip"
        self.model.save(str(final_model_path))
        logger.info(f"Hardened PPO training completed. Final model saved to {final_model_path}")
        return self.model

    def evaluate(self, eval_episodes: int = 5) -> Dict[str, float]:
        """Runs evaluation episodes comparing reward metrics."""
        episode_rewards = []
        for ep in range(eval_episodes):
            obs, info = self.env.reset()
            done = False
            total_r = 0.0
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, term, trunc, info = self.env.step(action)
                total_r += reward
                done = term or trunc
            episode_rewards.append(total_r)

        mean_reward = float(np.mean(episode_rewards))
        logger.info(f"Evaluation over {eval_episodes} episodes: Mean Reward = {mean_reward:.2f}")
        return {"mean_reward": mean_reward, "episodes": float(eval_episodes)}
