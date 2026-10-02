from pyboy import PyBoy
from pathlib import Path

class PokemonEmulator:

    def __init__(self, rom_path):
        rom=Path(rom_path)
        if(not rom.exists()):
            raise FileNotFoundError(f"Rom not found: {rom.absolute()}")
        
        self.pyboy = PyBoy(str(rom),window="SDL2")
        self.game = self.pyboy.game_wrapper

    def run(self):
        while self.pyboy.tick():
            pass

    def skip_intro(self):
        for _ in range(300):
            if not self.pyboy.tick():
                return False

        self.pyboy.button_press("start")
        for _ in range(5):
            self.pyboy.tick()
        self.pyboy.button_release("start")

        self.pyboy.button_press("a")
        for _ in range(5):
            self.pyboy.tick()
        self.pyboy.button_release("a")

        for _ in range(120):
            if not self.pyboy.tick():
                return False

        return True

    def save_state(self, output_path):
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with output.open("wb") as state_file:
            self.pyboy.save_state(state_file)

    def load_state(self, input_path):
        with Path(input_path).open("rb") as state_file:
            self.pyboy.load_state(state_file)

    def press(self, button, delay=1):
        self.pyboy.button(button, delay)

    def read_memory_range(self, start, length):
        return self.pyboy.memory[start:start + length]        

    def stop(self):
        self.pyboy.stop()

    def tick(self, frames=1):
        return self.pyboy.tick(frames)      

    def screenshot(self, output_path="screenshots/game.png"):
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        image = self.pyboy.screen.image
        image.save(output)

        print(f"Screenshot saved: {output.absolute()}")
