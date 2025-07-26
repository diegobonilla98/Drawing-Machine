import yaml

# Load calibration YAML
import os

with open(os.path.join(os.path.dirname(__file__), "calibration.yaml"), "r") as f:
    config = yaml.safe_load(f)["plotter_calibration"]

X = config["axes"]["X"]
Y = config["axes"]["Y"]

# --- Helper functions ---
def mm_to_steps_X(mm):
    slope = X["mm_to_steps"]["slope"]
    intercept = X["mm_to_steps"]["intercept"]
    # Clamp to limits
    mm = max(0, min(mm, X["physical_limit_mm"]))
    return int(round(slope * mm + intercept))

def mm_to_steps_Y(mm):
    slope = Y["mm_to_steps"]["slope"]
    intercept = Y["mm_to_steps"]["intercept"]
    mm = max(0, min(mm, Y["physical_limit_mm"]))
    return int(round(slope * mm + intercept))

def steps_to_mm_X(steps):
    slope = X["steps_to_mm"]["slope"]
    intercept = X["steps_to_mm"]["intercept"]
    return slope * steps + intercept

def steps_to_mm_Y(steps):
    slope = Y["steps_to_mm"]["slope"]
    intercept = Y["steps_to_mm"]["intercept"]
    return slope * steps + intercept


if __name__ == "__main__":
    # --- Example usage ---
    target_x_mm = 100
    target_y_mm = 130

    x_steps = mm_to_steps_X(target_x_mm)
    y_steps = mm_to_steps_Y(target_y_mm)
    print(f"Go to (X={target_x_mm} mm, Y={target_y_mm} mm):")
    print(f"   -> X = {x_steps} steps, Y = {y_steps} steps")

    # Read-back: Convert steps to physical position
    print("Measured back from steps:")
    print(f"   X: {steps_to_mm_X(x_steps):.3f} mm")
    print(f"   Y: {steps_to_mm_Y(y_steps):.3f} mm")
