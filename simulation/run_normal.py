
from pathlib import Path
from pyswmm import Simulation

# Get the project folder automatically
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Locate the SWMM input file
MODEL_PATH = PROJECT_DIR/ "sewer_module"/ "models" / "bluepulse_sewer.inp"

print("Starting BluePulse sewer simulation...")
print("Looking for model at:", MODEL_PATH)

# Check whether the file exists
if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"SWMM model not found: {MODEL_PATH}"
    )

# Run the simulation
with Simulation(str(MODEL_PATH)) as sim:
    for step in sim:
        pass

print("Simulation completed successfully!")
