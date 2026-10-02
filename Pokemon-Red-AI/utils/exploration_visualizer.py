from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def save_exploration_map(agent_paths, output_path="screenshots/agent_exploration.png"):
    maps = defaultdict(list)
    for agent_index, path in enumerate(agent_paths):
        for map_id, x, y in path:
            maps[map_id].append((agent_index, x, y))

    if not maps:
        return

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(
        1,
        len(maps),
        figsize=(6 * len(maps), 5),
        squeeze=False,
    )
    axes = axes[0]
    colors = plt.get_cmap("tab10")

    for axis, (map_id, points) in zip(axes, sorted(maps.items())):
        for agent_index in range(len(agent_paths)):
            agent_points = [
                (x, y)
                for current_agent, x, y in points
                if current_agent == agent_index
            ]
            if not agent_points:
                continue
            x_values, y_values = zip(*agent_points)
            axis.scatter(
                x_values[-1],
                y_values[-1],
                color=colors(agent_index % 10),
                s=35,
                label=f"Agent {agent_index + 1}",
            )

        axis.set_title(f"Map {map_id}")
        axis.set_xlabel("X")
        axis.set_ylabel("Y")
        axis.invert_yaxis()
        axis.grid(alpha=0.25)
        axis.legend()

    figure.suptitle("Combined Agent Exploration")
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
