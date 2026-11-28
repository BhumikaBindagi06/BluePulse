
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# Load normal and blockage datasets
normal = pd.read_csv(DATA_DIR / "normal_readings.csv")
blockage = pd.read_csv(DATA_DIR / "blockage_readings.csv")

# Calculate normal operating depth at J2
normal_j2_mean = normal["J2_depth_m"].mean()

# Define an initial detection threshold
threshold = normal_j2_mean * 1.20

print("Normal J2 average depth:", normal_j2_mean)
print("Anomaly threshold:", threshold)

# Detect abnormal J2 depth readings
blockage["anomaly"] = (
    blockage["J2_depth_m"] > threshold
)

# Count abnormal readings
anomaly_count = blockage["anomaly"].sum()

print("\n========== ANOMALY DETECTION RESULTS ==========")

print("Total readings:", len(blockage))
print("Abnormal readings:", anomaly_count)
print("Normal readings:", len(blockage) - anomaly_count)

print(
    "Percentage abnormal:",
    round(anomaly_count / len(blockage) * 100, 2),
    "%"
)

# Save detected anomalies
anomalies = blockage[blockage["anomaly"]]

anomalies.to_csv(
    DATA_DIR / "detected_anomalies.csv",
    index=False
)

print("\nDetected anomalies saved successfully!")
