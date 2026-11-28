
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# Load both datasets
normal = pd.read_csv(DATA_DIR / "normal_readings.csv")
blockage = pd.read_csv(DATA_DIR / "blockage_readings.csv")

# Convert timestamps
normal["timestamp"] = pd.to_datetime(normal["timestamp"])
blockage["timestamp"] = pd.to_datetime(blockage["timestamp"])

print("\n========== DATASET COMPARISON ==========")

print("Normal readings:", len(normal))
print("Blockage readings:", len(blockage))

# Compare average and maximum pipe flows
print("\n========== PIPE FLOW COMPARISON ==========")

for pipe in ["C1", "C2", "C3"]:
    column = f"{pipe}_flow_cms"

    print(f"\n{pipe}")
    print("Normal average:", normal[column].mean())
    print("Blockage average:", blockage[column].mean())
    print("Normal maximum:", normal[column].max())
    print("Blockage maximum:", blockage[column].max())

# Compare junction depths
print("\n========== JUNCTION DEPTH COMPARISON ==========")

for node in ["J1", "J2", "J3"]:
    column = f"{node}_depth_m"

    print(f"\n{node}")
    print("Normal average:", normal[column].mean())
    print("Blockage average:", blockage[column].mean())

# Plot pipe flows
plt.figure(figsize=(12, 6))

for pipe in ["C1", "C2", "C3"]:
    column = f"{pipe}_flow_cms"

    plt.plot(
        normal[column].values,
        label=f"{pipe} Normal"
    )

    plt.plot(
        blockage[column].values,
        linestyle="--",
        label=f"{pipe} Blockage"
    )

plt.xlabel("Simulation Reading")
plt.ylabel("Flow (CMS)")
plt.title("Normal vs Blockage - Pipe Flow")
plt.legend()
plt.grid(True)
plt.tight_layout()

plt.savefig(DATA_DIR / "normal_vs_blockage_flow.png")
plt.show()

# Plot junction depths
plt.figure(figsize=(12, 6))

for node in ["J1", "J2", "J3"]:
    column = f"{node}_depth_m"

    plt.plot(
        normal[column].values,
        label=f"{node} Normal"
    )

    plt.plot(
        blockage[column].values,
        linestyle="--",
        label=f"{node} Blockage"
    )

plt.xlabel("Simulation Reading")
plt.ylabel("Water Depth (m)")
plt.title("Normal vs Blockage - Manhole Depth")
plt.legend()
plt.grid(True)
plt.tight_layout()

plt.savefig(DATA_DIR / "normal_vs_blockage_depth.png")
plt.show()

print("\nComparison completed!")
