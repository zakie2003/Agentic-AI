import msvcrt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from emulator.game import PokemonEmulator


ROM_PATH = "roms/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb"
STATE_PATH = Path("saves/pokemon_overworld.state")


def main():
    emulator = PokemonEmulator(ROM_PATH)

    try:
        print("Booting Pokémon Red...")
        for _ in range(300):
            if not emulator.tick():
                return

        print("Navigate to the overworld manually in the PyBoy window.")
        print("Press ENTER in this terminal when you are ready to save the state.")

        while True:
            if not emulator.tick():
                return

            if msvcrt.kbhit() and msvcrt.getwch() == "\r":
                emulator.save_state(STATE_PATH)
                print(f"Saved state to {STATE_PATH}")
                return
    finally:
        emulator.stop()


if __name__ == "__main__":
    main()
