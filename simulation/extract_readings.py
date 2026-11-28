
from pathlib import Path
import pandas as pd

from pyswmm import Simulation, Nodes, Links

# 1. Locate the BluePulse project folder
PROJECT_DIR = Path(__file__).resolve().parent.parent

# 2. Locate the SWMM model
MODEL_PATH = (
    PROJECT_DIR / "sewer_module" / "models" / "bluepulse_sewer.inp"
)

# 3. Location where CSV readings will be saved
OUTPUT_PATH = PROJECT_DIR / "data" / "normal_readings.csv"

print("Starting BluePulse data extraction...")

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

# Our SWMM object IDs
node_ids = ["J1", "J2", "J3", "O1"]
link_ids = ["1", "2", "3"]

readings = []

# 4. Open and run the SWMM simulation
with Simulation(str(MODEL_PATH)) as sim:

    nodes = Nodes(sim)
    links = Links(sim)

    # Get the individual node and pipe objects
    node_objects = {name: nodes[name] for name in node_ids}
    link_objects = {name: links[name] for name in link_ids}

    # 5. Collect readings at every simulation step
    for step in sim:

        row = {
            "timestamp": sim.current_time
        }

        # Collect manhole water depths
        for name, node in node_objects.items():
            row[f"{name}_depth_m"] = node.depth

        # Collect pipe flow and velocity
        for name, link in link_objects.items():
            row[f"C{name}_flow_cms"] = link.flow
            row[f"C{name}_velocity_mps"] = link.depth

        readings.append(row)

# 6. Convert readings into a DataFrame
df = pd.DataFrame(readings)

# 7. Export readings to CSV
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUTPUT_PATH, index=False)

print("\nSimulation and extraction completed!")
print("Total readings:", len(df))
print("CSV saved at:", OUTPUT_PATH)

print("\nFirst five readings:")
print(df.head())
