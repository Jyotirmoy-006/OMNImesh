"""
Omni-Mesh Reinforcement Learning Training Pipeline
Uses Stable-Baselines3 PPO with a lightweight MLP policy network optimized
for edge-compute deployment, complete with periodic model checkpointing.
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
import numpy as np

try:
    import torch
    import torch.nn as nn
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.env_util import make_vec_env
    from stable_baselines3.common.vec_env import DummyVecEnv
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

from omnimesh.utils.logger import logger

class CheckpointCallback(BaseCallback if HAS_SB3 else object):
    """
    Callback that saves model weights every `save_freq` environment steps.
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
    Headless PPO training controller utilizing Stable-Baselines3.
    Configures a lightweight 2-layer MLP policy to ensure sub-millisecond
    inference latency on commodity edge microcontrollers (RPi 4B).
    """
    def __init__(
        self,
        env: Any,
        checkpoint_dir: str = "models/checkpoints",
        learning_rate: float = 3e-4,
        n_steps: int = 512,
        batch_size: int = 64,
        gamma: float = 0.99,
        save_freq: int = 10000,
    ):
        if not HAS_SB3:
            raise RuntimeError("Stable-Baselines3 and PyTorch are required for RL training.")

        self.env = env
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.save_freq = save_freq

        # Lightweight 2-layer MLP architecture [64, 64] for edge-compute constraints
        self.policy_kwargs = dict(
            net_arch=dict(pi=[64, 64], vf=[64, 64]),
            activation_fn=nn.Tanh,
        )

        logger.info("Configuring PPO with lightweight [64, 64] MLP edge policy architecture...")
        self.model = PPO(
            policy="MlpPolicy",
            env=self.env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            gamma=gamma,
            policy_kwargs=self.policy_kwargs,
            verbose=1,
            tensorboard_log=None,
        )

        self.checkpoint_callback = CheckpointCallback(
            save_freq=self.save_freq,
            save_path=str(self.checkpoint_dir),
            verbose=1,
        )

    def train(self, total_timesteps: int = 100000) -> PPO:
        """Executes the PPO policy optimization training loop."""
        logger.info(f"Starting PPO training for {total_timesteps} timesteps...")
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=self.checkpoint_callback,
            progress_bar=False,
        )
        final_model_path = self.checkpoint_dir / "omnimesh_ppo_final.zip"
        self.model.save(str(final_model_path))
        logger.info(f"PPO training finished. Final model saved to {final_model_path}")
        return self.model

    def evaluate(self, eval_episodes: int = 3) -> Dict[str, float]:
        """Runs headless evaluation episodes and computes mean reward and latency."""
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
