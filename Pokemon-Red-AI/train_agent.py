from pathlib import Path
import time

import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from environment.pokemon_env import PokemonRedEnv
from utils.exploration_visualizer import save_exploration_map
from utils.live_visualizer import LiveMapServer
from utils.video_recorder import create_gif_writer


CONFIG_PATH = Path("config/config.yaml")
MODEL_PATH = Path("models/pokemon_ppo")
TOTAL_TIMESTEPS = 10_000_000
CHECKPOINT_DIR = Path("models/checkpoints")


class ProgressCallback(BaseCallback):

    def __init__(
        self,
        checkpoint_interval=1_000,
        max_duration_seconds=None,
        trajectory_memory=None,
        verbose=0,
    ):
        super().__init__(verbose)
        self.checkpoint_interval = checkpoint_interval
        self.next_checkpoint = checkpoint_interval
        self.max_duration_seconds = max_duration_seconds
        self.start_time = None
        self.trajectory_memory = trajectory_memory

    def _on_training_start(self):
        self.start_time = time.monotonic()

    def _on_step(self):
        if (
            self.max_duration_seconds is not None
            and time.monotonic() - self.start_time >= self.max_duration_seconds
        ):
            print("Training time limit reached.")
            return False

        if self.num_timesteps >= self.next_checkpoint:
            CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
            self.model.save(CHECKPOINT_DIR / f"pokemon_ppo_{self.num_timesteps}")
            if self.trajectory_memory is not None:
                save_exploration_map(self.trajectory_memory)
            self.next_checkpoint += self.checkpoint_interval

        for info in self.locals.get("infos", []):
            if info.get("stage_reached", False):
                stage_name = info.get("stage_name", info["stage_index"])
                safe_name = "".join(
                    character if character.isalnum() or character in "-_"
                    else "_"
                    for character in str(stage_name)
                )
                stage_path = CHECKPOINT_DIR / f"pokemon_ppo_stage_{safe_name}"
                CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
                self.model.save(stage_path)
                print(f"Stage reached. Saved {stage_path}.zip")

            if info.get("goal_reached", False):
                MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
                self.model.save(MODEL_PATH.with_name("pokemon_ppo_goal"))
                print("Goal reached. Saved models/pokemon_ppo_goal.zip")
                return False

        return True


def main():
    with CONFIG_PATH.open("r") as config_file:
        config = yaml.safe_load(config_file)

    training_config = config.get("training", {}).copy()
    resume = training_config.pop("resume", False)
    num_envs = training_config.pop("num_envs", 1)
    visible_agents = training_config.pop("visible_agents", 0)
    window_mode = training_config.pop("window", "null")
    training_hours = training_config.pop("training_hours", None)
    total_timesteps = training_config.pop("total_timesteps", TOTAL_TIMESTEPS)
    video_enabled = training_config.pop("video_enabled", False)
    video_path = training_config.pop(
        "video_path", "screenshots/agent_0_training.gif"
    )
    video_fps = training_config.pop("video_fps", 10)
    video_frame_interval = training_config.pop("video_frame_interval", 1)
    live_visualization = training_config.pop("live_visualization", False)
    live_visualization_port = training_config.pop("live_visualization_port", 8765)
    screen_memory = []
    trajectory_memory = [[] for _ in range(num_envs)]
    live_server = (
        LiveMapServer(trajectory_memory, port=live_visualization_port)
        if live_visualization else None
    )
    if live_server is not None:
        live_server.start()
        print(f"Live map: http://127.0.0.1:{live_visualization_port}")
    video_writer = (
        create_gif_writer(video_path, video_fps)
        if video_enabled and visible_agents > 0
        else None
    )

    def make_env(index):
        return PokemonRedEnv(
            config["emulator"]["rom_path"],
            goal_state=config.get("goal"),
            stages=config.get("stages"),
            reward_config=config.get("rewards"),
            window=window_mode if index < visible_agents else "null",
            screen_memory=screen_memory,
            trajectory_memory=trajectory_memory[index],
            video_writer=video_writer if index == 0 else None,
            video_frame_interval=video_frame_interval,
            **training_config,
        )

    env = DummyVecEnv(
        [lambda index=index: make_env(index) for index in range(num_envs)]
    )
    model_exists = MODEL_PATH.with_suffix(".zip").exists()
    if resume and model_exists:
        model = PPO.load(MODEL_PATH, env=env)
        print(f"Loaded model from {MODEL_PATH}.zip")
    else:
        model = PPO(
            "CnnPolicy",
            env,
            verbose=1,
            n_steps=128,
            batch_size=32,
        )

    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=ProgressCallback(
                max_duration_seconds=(training_hours * 60 * 60)
                if training_hours is not None else None,
                trajectory_memory=trajectory_memory,
            ),
            reset_num_timesteps=not (resume and model_exists),
        )
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.save(MODEL_PATH)
        print(f"Saved model to {MODEL_PATH}.zip")
    finally:
        env.close()
        if live_server is not None:
            live_server.stop()


if __name__ == "__main__":
    main()
