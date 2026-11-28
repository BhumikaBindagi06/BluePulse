
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

normal = pd.read_csv(DATA_DIR / "normal_readings.csv")
blockage = pd.read_csv(DATA_DIR / "blockage_readings.csv")

nodes = ["J1", "J2", "J3"]

# Store detected events
results = blockage.copy()

print("\n========== MULTI-NODE ANOMALY DETECTION ==========")

for node in nodes:

    column = f"{node}_depth_m"

    # Calculate normal baseline
    baseline = normal[column].mean()

    # Set threshold 20% above normal average
    threshold = baseline * 1.20

    # Detect abnormal readings
    anomaly_column = f"{node}_anomaly"

    results[anomaly_column] = (
        results[column] > threshold
    )

    count = results[anomaly_column].sum()

    print(f"\nNode: {node}")
    print("Normal average:", round(baseline, 6))
    print("Detection threshold:", round(threshold, 6))
    print("Abnormal readings:", count)

# Identify readings where any node is abnormal
anomaly_columns = [
    f"{node}_anomaly" for node in nodes
]

results["any_anomaly"] = results[anomaly_columns].any(axis=1)

# Save results
results.to_csv(
    DATA_DIR / "multi_node_anomalies.csv",
    index=False
)

print("\nMulti-node detection completed!")
print("Saved: multi_node_anomalies.csv")

