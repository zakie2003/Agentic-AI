from pathlib import Path

import imageio.v2 as imageio


def create_gif_writer(output_path, fps=10):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    return imageio.get_writer(
        output,
        mode="I",
        duration=1 / fps,
        loop=0,
    )
