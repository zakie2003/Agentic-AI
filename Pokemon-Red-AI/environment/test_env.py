import yaml

from pokemon_env import PokemonRedEnv


def main():

    with open("config/config.yaml", "r") as file:

        config = yaml.safe_load(file)

    rom_path = config["emulator"]["rom_path"]

    env = PokemonRedEnv(rom_path)

    print("Observation space:")
    print(env.observation_space)

    print("\nAction space:")
    print(env.action_space)

    observation, info = env.reset()

    print("\nObservation shape:")
    print(observation.shape)

    for i in range(10):

        action = env.action_space.sample()

        observation, reward, terminated, truncated, info = env.step(
            action
        )

        print(
            f"Step {i + 1}: "
            f"action={action}, "
            f"reward={reward}"
        )

    env.close()


if __name__ == "__main__":
    main()