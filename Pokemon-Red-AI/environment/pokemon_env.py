from collections import deque
from pathlib import Path

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from pyboy import PyBoy


BATTLE_STATE_ADDRESS = 0xD057
PARTY_COUNT_ADDRESS = 0xD163
POKEDEX_OWNED_ADDRESS = 0xD2F7
POKEDEX_OWNED_BYTES = 19


class PokemonRedEnv(gym.Env):

    metadata = {
        "render_modes": ["human"]
    }

    def __init__(
        self,
        rom_path,
        state_path="saves/pokemon_overworld.state",
        goal_state=None,
        stages=None,
        reward_config=None,
        window="null",
        frame_skip=4,
        observation_width=80,
        observation_height=72,
        frame_history=4,
        stuck_steps=50,
        recovery_steps=8,
        screen_memory=None,
        screen_match_threshold=0.08,
        trajectory_memory=None,
        video_writer=None,
        video_frame_interval=1,
    ):

        super().__init__()

        self.rom_path = rom_path
        self.state_path = Path(state_path)
        self.stages = list(stages or ([goal_state] if goal_state else []))
        self.stage_index = 0
        self.window = window
        self.frame_skip = frame_skip
        self.observation_width = observation_width
        self.observation_height = observation_height
        self.frame_history = frame_history
        self.stuck_steps = stuck_steps
        self.recovery_steps = recovery_steps
        self.screen_match_threshold = screen_match_threshold
        self.steps_without_progress = 0
        self.previous_episode_stuck = False
        self.rewards = {
            "idle": -0.001,
            "blocked": -0.05,
            "reverse": -0.03,
            "revisit": -0.12,
            "move": 0.1,
            "new_position": 0.05,
            "new_map": 1.0,
            "new_screen": 1.0,
            "battle": 2.0,
            "new_pokemon": 5.0,
            "goal": 10.0,
            "stuck": -2.0,
            **(reward_config or {}),
        }

        self.pyboy = None

        self.observation_space = spaces.Box(
            low=0,
            high=255,
            shape=(
                self.observation_height,
                self.observation_width,
                self.frame_history,
            ),
            dtype=np.uint8
        )

        self.action_space = spaces.Discrete(7)

        self.actions = {
            0: None,
            1: "up",
            2: "down",
            3: "left",
            4: "right",
            5: "a",
            6: "b"
        }

        self._previous_observation = None
        self._previous_position = None
        self._previous_map = None
        self._visited_positions = set()
        self._visited_maps = set()
        self._previous_action = None
        self._previous_battle_state = None
        self._previous_party_count = 0
        self._previous_owned_count = 0
        self._frame_buffer = deque(maxlen=self.frame_history)
        self._seen_screens = screen_memory if screen_memory is not None else []
        self._trajectory_memory = trajectory_memory if trajectory_memory is not None else []
        self._video_writer = video_writer
        self._video_frame_interval = max(1, video_frame_interval)
        self._video_frame_count = 0
        self._last_screen_is_new = False
        self._start_emulator()

    def _start_emulator(self):

        self.pyboy = PyBoy(
            self.rom_path,
            window=self.window,
            sound_emulated=False
        )

        if self.state_path.exists():
            with self.state_path.open("rb") as state_file:
                self.pyboy.load_state(state_file)
        else:
            for _ in range(300):
                self.pyboy.tick()

    def _get_observation(self):

        image = self.pyboy.screen.image.convert("L")
        if (
            self._video_writer is not None
            and self._video_frame_count % self._video_frame_interval == 0
        ):
            self._video_writer.append_data(
                np.asarray(self.pyboy.screen.image.convert("RGB"))
            )
        self._video_frame_count += 1
        image = image.resize((self.observation_width, self.observation_height))
        frame = np.asarray(image, dtype=np.uint8)[..., np.newaxis]
        screen_sample = frame[::8, ::8, 0].astype(np.float32) / 255.0
        self._last_screen_is_new = not any(
            np.mean(np.abs(screen_sample - seen_screen))
            <= self.screen_match_threshold
            for seen_screen in self._seen_screens
        )
        if self._last_screen_is_new:
            self._seen_screens.append(screen_sample.copy())
        self._frame_buffer.append(frame)
        while len(self._frame_buffer) < self.frame_history:
            self._frame_buffer.appendleft(frame.copy())
        return np.concatenate(tuple(self._frame_buffer), axis=2)

    def _get_position(self):
        return (
            self.pyboy.memory[0xD361],
            self.pyboy.memory[0xD362],
        )

    def _get_map(self):
        return self.pyboy.memory[0xD35E]

    def _get_battle_state(self):
        return self.pyboy.memory[BATTLE_STATE_ADDRESS]

    def _get_party_count(self):
        return self.pyboy.memory[PARTY_COUNT_ADDRESS]

    def _get_owned_count(self):
        owned_flags = self.pyboy.memory[
            POKEDEX_OWNED_ADDRESS:POKEDEX_OWNED_ADDRESS + POKEDEX_OWNED_BYTES
        ]
        return sum(byte.bit_count() for byte in owned_flags)

    def _is_stage_reached(self, stage, position, map_id):
        checks = {
            "map_id": map_id,
            "x": position[1],
            "y": position[0],
        }

        active_checks = {
            key: value
            for key, value in stage.items()
            if value is not None and key in checks
        }

        return bool(active_checks) and all(
            checks[key] == value
            for key, value in active_checks.items()
        )

    def _current_stage(self):
        if self.stage_index >= len(self.stages):
            return None
        return self.stages[self.stage_index]

    def _distance_to_stage(self, stage, position, map_id):
        if not stage or stage.get("map_id") != map_id:
            return None
        if stage.get("x") is None or stage.get("y") is None:
            return None
        return abs(position[1] - stage["x"]) + abs(position[0] - stage["y"])

    def step(self, action):

        button = self.actions[int(action)]

        if button is not None:
            self.pyboy.button_press(button)

        running = True
        for _ in range(self.frame_skip):
            if not self.pyboy.tick():
                running = False
                break

        if button is not None:
            self.pyboy.button_release(button)

        observation = self._get_observation()
        new_screen = self._last_screen_is_new

        position = self._get_position()
        map_id = self._get_map()
        if position != self._previous_position:
            self._trajectory_memory.append((map_id, position[1], position[0]))
        battle_state = self._get_battle_state()
        party_count = self._get_party_count()
        owned_count = self._get_owned_count()
        reward = self.rewards["idle"]
        if new_screen:
            reward += self.rewards["new_screen"]
        battle_started = (
            battle_state in (1, 2)
            and self._previous_battle_state not in (1, 2)
        )
        new_pokemon = (
            party_count > self._previous_party_count
            or owned_count > self._previous_owned_count
        )
        if battle_started:
            reward += self.rewards["battle"]
        if new_pokemon:
            reward += self.rewards["new_pokemon"]
        opposites = {1: 2, 2: 1, 3: 4, 4: 3}

        if int(action) in opposites and opposites[int(action)] == self._previous_action:
            reward += self.rewards["reverse"]

        if position != self._previous_position:
            self.steps_without_progress = 0
            reward += self.rewards["move"]
            if position in self._visited_positions:
                reward += self.rewards["revisit"]
            else:
                reward += self.rewards["new_position"]
                self._visited_positions.add(position)
        elif int(action) in (1, 2, 3, 4):
            self.steps_without_progress += 1
            reward += self.rewards["blocked"]
        else:
            self.steps_without_progress += 1

        if map_id != self._previous_map and map_id not in self._visited_maps:
            reward += self.rewards["new_map"]
            self._visited_maps.add(map_id)

        stage = self._current_stage()
        previous_distance = self._distance_to_stage(
            stage, self._previous_position, self._previous_map
        ) if self._previous_position is not None else None
        current_distance = self._distance_to_stage(stage, position, map_id)
        if previous_distance is not None and current_distance is not None:
            reward += (
                previous_distance - current_distance
            ) * self.rewards["distance"]

        stage_reached = bool(
            stage and self._is_stage_reached(stage, position, map_id)
        )
        completed_stage = None
        if stage_reached:
            completed_stage = stage.get("name", self.stage_index + 1)
            reward += self.rewards["goal"]
            self.stage_index += 1

        goal_reached = stage_reached and self.stage_index >= len(self.stages)
        stuck = (
            self.stuck_steps > 0
            and self.steps_without_progress >= self.stuck_steps
        )
        if stuck:
            reward += self.rewards["stuck"]
            self.previous_episode_stuck = True

        self._previous_observation = observation.copy()
        self._previous_position = position
        self._previous_map = map_id
        self._previous_action = int(action)
        self._previous_battle_state = battle_state
        self._previous_party_count = party_count
        self._previous_owned_count = owned_count

        terminated = not running or goal_reached or stuck

        truncated = False

        info = {
            "goal_reached": goal_reached,
            "stage_reached": stage_reached,
            "stage_index": self.stage_index,
            "stage_name": completed_stage,
            "stuck": stuck,
            "new_screen": new_screen,
            "battle_started": battle_started,
            "new_pokemon": new_pokemon,
            "steps_without_progress": self.steps_without_progress,
            "map_id": map_id,
            "x": position[1],
            "y": position[0],
        }

        return (
            observation,
            reward,
            terminated,
            truncated,
            info
        )

    def reset(self, seed=None, options=None):

        super().reset(seed=seed)

        was_stuck = self.previous_episode_stuck
        if not was_stuck:
            if self.pyboy is not None:
                self.pyboy.stop()

            self._start_emulator()

        self._frame_buffer.clear()

        if self.previous_episode_stuck and self.recovery_steps > 0:
            for _ in range(self.recovery_steps):
                button = self.actions[int(self.np_random.integers(1, 5))]
                self.pyboy.button_press(button)
                for _ in range(self.frame_skip):
                    if not self.pyboy.tick():
                        break
                self.pyboy.button_release(button)

        observation = self._get_observation()
        self._previous_observation = observation.copy()
        self._previous_position = self._get_position()
        self._previous_map = self._get_map()
        self._trajectory_memory.append(
            (self._previous_map, self._previous_position[1], self._previous_position[0])
        )
        self._visited_positions = {self._previous_position}
        self._visited_maps = {self._previous_map}
        self._previous_action = None
        self._previous_battle_state = self._get_battle_state()
        self._previous_party_count = self._get_party_count()
        self._previous_owned_count = self._get_owned_count()
        if not was_stuck:
            self.stage_index = 0
        self.steps_without_progress = 0
        self.previous_episode_stuck = False

        return observation, {}

    def render(self):

        pass

    def close(self):

        if self.pyboy is not None:

            self.pyboy.stop()
            self.pyboy = None

        if self._video_writer is not None:
            self._video_writer.close()
            self._video_writer = None