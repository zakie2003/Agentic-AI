from emulator.game import PokemonEmulator
from pathlib import Path
import yaml

CONFIG_PATH = "config/config.yaml"
STATE_PATH = Path("saves/pokemon_overworld.state")


def load_config():
    with open(CONFIG_PATH, "r") as file:
        return yaml.safe_load(file)

def main():

    config = load_config()
    rom_path = config["emulator"]["rom_path"]
    emulator = PokemonEmulator(rom_path)
    print(f"Loading ROM: {rom_path}")
    try:
        if STATE_PATH.exists():
            emulator.load_state(STATE_PATH)
            print(f"Loaded save state: {STATE_PATH}")
        elif not emulator.skip_intro():
            return
        emulator.run()
    finally:
        emulator.stop()


if __name__ == "__main__":
    main()