from pathlib import Path

from pyboy import PyBoy


ROM_PATH = "roms/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb"
STATE_PATH = Path("saves/pokemon_overworld.state")


def main():
    pyboy = PyBoy(ROM_PATH, window="SDL2")

    try:
        with STATE_PATH.open("rb") as state_file:
            pyboy.load_state(state_file)

        print("Move in the PyBoy window. Close it to stop.")
        previous_position = None

        while pyboy.tick():
            map_id = pyboy.memory[0xD35E]
            y = pyboy.memory[0xD361]
            x = pyboy.memory[0xD362]
            position = (map_id, x, y)

            if position != previous_position:
                print(f"Map ID: {map_id}, X: {x}, Y: {y}", flush=True)
                previous_position = position
    finally:
        pyboy.stop()


if __name__ == "__main__":
    main()
