
from pathlib import Path
import pandas as pd
from pyswmm import Simulation, Nodes, Links

# Project paths
PROJECT_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = (
    PROJECT_DIR / "sewer_module" / "models"
    / "bluepulse_blockage.inp"
)

OUTPUT_PATH = PROJECT_DIR / "data" / "blockage_readings.csv"

print("Starting BluePulse blockage simulation...")

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

node_ids = ["J1", "J2", "J3", "O1"]
link_ids = ["1", "2", "3"]

readings = []

with Simulation(str(MODEL_PATH)) as sim:

    nodes = Nodes(sim)
    links = Links(sim)

    node_objects = {name: nodes[name] for name in node_ids}
    link_objects = {name: links[name] for name in link_ids}

    for step in sim:

        row = {"timestamp": sim.current_time}

        # Manhole water depths
        for name, node in node_objects.items():
            row[f"{name}_depth_m"] = node.depth

        # Pipe flow and water velocity
        for name, link in link_objects.items():
            row[f"C{name}_flow_cms"] = link.flow
            row[f"C{name}_depth_m"] = link.depth

        readings.append(row)

df = pd.DataFrame(readings)

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUTPUT_PATH, index=False)

print("\nBlockage simulation completed!")
print("Total readings:", len(df))
print("Saved to:", OUTPUT_PATH)
print("\nFirst five readings:")
print(df.head())
