from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from battery_pdm.pipeline import build_final_artifacts


def find_project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in current.parents:
        if (parent / "data").exists() and (parent / "notebooks").exists():
            return parent

    raise FileNotFoundError("Battery_TimeSeries_Analysis project root not found.")


def main() -> None:
    project_root = find_project_root()
    artifacts = build_final_artifacts(project_root)

    print(f"project_root: {project_root}")
    print(f"scenarios: {artifacts['scenarios'].shape}")
    print(f"forecasts: {artifacts['forecasts'].shape}")
    print(f"forecast_metrics: {artifacts['forecast_metrics'].shape}")
    print(f"rul_predictions: {artifacts['rul_predictions'].shape}")
    print(f"rul_metrics: {artifacts['rul_metrics'].shape}")
    print()
    print("decision_leaderboard")
    print(artifacts["decision_leaderboard"].to_string(index=False))


if __name__ == "__main__":
    main()
