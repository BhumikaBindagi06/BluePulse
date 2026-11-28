
from pathlib import Path
import pandas as pd

# Locate the dataset
PROJECT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_DIR / "data" / "normal_readings.csv"

# Load the dataset
df = pd.read_csv(CSV_PATH)

print("\n========== DATASET INFORMATION ==========")

print("\nShape:")
print(df.shape)

print("\nColumn names:")
print(df.columns.tolist())

print("\nMissing values:")
print(df.isnull().sum())

print("\nStatistical summary:")
print(df.describe())

# Check flow in each pipe
print("\n========== PIPE FLOW ANALYSIS ==========")

for pipe in ["C1", "C2", "C3"]:
    column = f"{pipe}_flow_cms"

    print(f"\n{pipe}:")
    print("Minimum flow:", df[column].min())
    print("Maximum flow:", df[column].max())
    print("Average flow:", df[column].mean())

print("\nData inspection completed!")
