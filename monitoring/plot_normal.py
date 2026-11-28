
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# Locate dataset
PROJECT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_DIR / "data" / "normal_readings.csv"

df = pd.read_csv(CSV_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Convert time into elapsed minutes
df["elapsed_minutes"] = (
    df["timestamp"] - df["timestamp"].iloc[0]
).dt.total_seconds() / 60

# Graph 1: Flow through all three pipes
plt.figure(figsize=(12, 5))

for pipe in ["C1", "C2", "C3"]:
    plt.plot(
        df["elapsed_minutes"],
        df[f"{pipe}_flow_cms"],
        label=pipe
    )

plt.xlabel("Elapsed Time (minutes)")
plt.ylabel("Flow (CMS)")
plt.title("Normal Sewer Network - Pipe Flow")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig(PROJECT_DIR / "data" / "normal_pipe_flow.png")
plt.show()

# Graph 2: Water depth at all junctions
plt.figure(figsize=(12, 5))

for node in ["J1", "J2", "J3"]:
    plt.plot(
        df["elapsed_minutes"],
        df[f"{node}_depth_m"],
        label=node
    )

plt.xlabel("Elapsed Time (minutes)")
plt.ylabel("Water Depth (m)")
plt.title("Normal Sewer Network - Manhole Water Depth")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig(PROJECT_DIR / "data" / "normal_node_depth.png")
plt.show()

print("Normal operating graphs generated!")
