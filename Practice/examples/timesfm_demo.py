from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import timesfm


def make_series(context: int) -> np.ndarray:
  rng = np.random.default_rng(7)
  x = np.arange(context, dtype=np.float32)
  trend = 0.015 * x
  seasonality = 0.8 * np.sin(x / 6.0) + 0.25 * np.sin(x / 21.0)
  noise = rng.normal(0.0, 0.05, size=context)
  return (trend + seasonality + noise).astype(np.float32)


def save_outputs(
    history: np.ndarray,
    point_forecast: np.ndarray,
    quantile_forecast: np.ndarray,
    output_dir: Path,
) -> None:
  output_dir.mkdir(parents=True, exist_ok=True)

  forecast_steps = np.arange(len(history), len(history) + len(point_forecast))
  csv_path = output_dir / "timesfm_demo_forecast.csv"
  p10 = quantile_forecast[:, 1]
  p90 = quantile_forecast[:, 9]

  rows = ["step,point_forecast,p10,p90"]
  rows.extend(
      f"{step},{point:.6f},{lo:.6f},{hi:.6f}"
      for step, point, lo, hi in zip(forecast_steps, point_forecast, p10, p90)
  )
  csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

  plt.figure(figsize=(10, 4.8))
  plt.plot(np.arange(len(history)), history, label="history", color="#335c67")
  plt.plot(forecast_steps, point_forecast, label="TimesFM forecast", color="#c44536")
  plt.fill_between(forecast_steps, p10, p90, color="#f4a261", alpha=0.25, label="p10-p90")
  plt.axvline(len(history) - 1, color="#777777", linewidth=1, linestyle="--")
  plt.title("TimesFM demo forecast")
  plt.xlabel("time step")
  plt.ylabel("value")
  plt.legend()
  plt.tight_layout()
  plt.savefig(output_dir / "timesfm_demo_forecast.png", dpi=160)
  plt.close()


def main() -> None:
  parser = argparse.ArgumentParser(description="Run a small TimesFM forecast demo.")
  parser.add_argument("--context", type=int, default=160)
  parser.add_argument("--horizon", type=int, default=12)
  parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
  args = parser.parse_args()

  torch.set_float32_matmul_precision("high")

  history = make_series(args.context)
  model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
      "google/timesfm-2.5-200m-pytorch"
  )
  model.compile(
      timesfm.ForecastConfig(
          max_context=max(1024, args.context),
          max_horizon=max(256, args.horizon),
          normalize_inputs=True,
          use_continuous_quantile_head=True,
          force_flip_invariance=True,
          infer_is_positive=False,
          fix_quantile_crossing=True,
      )
  )

  point_forecast, quantile_forecast = model.forecast(
      horizon=args.horizon,
      inputs=[history],
  )
  point = point_forecast[0]
  quantiles = quantile_forecast[0]

  save_outputs(history, point, quantiles, args.output_dir)

  print(f"Forecast shape: {point.shape}")
  print(f"Quantile shape: {quantiles.shape}")
  print(f"Wrote {args.output_dir / 'timesfm_demo_forecast.csv'}")
  print(f"Wrote {args.output_dir / 'timesfm_demo_forecast.png'}")


if __name__ == "__main__":
  main()
