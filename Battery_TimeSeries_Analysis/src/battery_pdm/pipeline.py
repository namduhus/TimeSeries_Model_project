from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


@dataclass(frozen=True)
class PipelinePaths:
    project_root: Path
    labeled_data_path: Path
    scenario_path: Path
    csv_output_dir: Path
    parquet_output_dir: Path


@dataclass(frozen=True)
class EvaluationConfig:
    target_col: str = "capacity_ah"
    target_name: str = "capacity_raw"
    model_family: str = "machine_learning"
    model_name: str = "RandomForestRegressor"
    eol_threshold: float = 0.80
    random_state: int = 42


def default_paths(project_root: Path) -> PipelinePaths:
    project_root = project_root.resolve()

    return PipelinePaths(
        project_root=project_root,
        labeled_data_path=project_root
        / "data"
        / "processed"
        / "paraquet"
        / "battery_cycles_labeled.parquet",
        scenario_path=project_root
        / "outputs"
        / "csv"
        / "evaluation"
        / "rolling_scenarios.csv",
        csv_output_dir=project_root
        / "outputs"
        / "csv"
        / "evaluation"
        / "final",
        parquet_output_dir=project_root
        / "outputs"
        / "parquet"
        / "evaluation"
        / "final",
    )


def load_modeling_series(paths: PipelinePaths) -> pd.DataFrame:
    battery_cycles = pd.read_parquet(paths.labeled_data_path)

    required_columns = {
        "cell_id",
        "cycle",
        "capacity_ah",
        "initial_capacity",
        "soh",
        "eol_threshold",
        "eol_confirmation_cycles",
        "eol_cycle",
        "is_modeling_cycle",
    }
    missing_columns = required_columns - set(battery_cycles.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    return (
        battery_cycles[battery_cycles["is_modeling_cycle"]]
        .sort_values("cycle")
        .reset_index(drop=True)
        .copy()
    )


def load_rolling_scenarios(paths: PipelinePaths) -> pd.DataFrame:
    scenarios = pd.read_csv(paths.scenario_path)

    required_columns = {
        "scenario_id",
        "scenario_type",
        "forecast_origin",
        "horizon",
        "true_eol_cycle",
        "true_rul",
        "includes_eol",
    }
    missing_columns = required_columns - set(scenarios.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required scenario columns: {sorted(missing_columns)}"
        )

    return scenarios.sort_values(
        ["scenario_type", "forecast_origin", "horizon", "scenario_id"]
    ).reset_index(drop=True)


def make_lag_features(input_df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    feature_df = input_df.copy()

    feature_df["lag_1"] = feature_df[target_col].shift(1)
    feature_df["lag_2"] = feature_df[target_col].shift(2)
    feature_df["lag_3"] = feature_df[target_col].shift(3)
    feature_df["lag_5"] = feature_df[target_col].shift(5)
    feature_df["lag_10"] = feature_df[target_col].shift(10)

    shifted_target = feature_df[target_col].shift(1)

    feature_df["rolling_mean_5"] = (
        shifted_target.rolling(window=5, min_periods=1).mean()
    )
    feature_df["rolling_mean_10"] = (
        shifted_target.rolling(window=10, min_periods=1).mean()
    )
    feature_df["rolling_std_10"] = (
        shifted_target.rolling(window=10, min_periods=2).std()
    )
    feature_df["cycle_norm"] = (
        feature_df["cycle"] / feature_df["cycle"].max()
    )

    return feature_df


def recursive_random_forest_forecast(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_col: str,
    random_state: int,
) -> np.ndarray:
    history_df = train_df.copy()
    predictions: list[float] = []

    feature_columns = [
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_5",
        "lag_10",
        "rolling_mean_5",
        "rolling_mean_10",
        "rolling_std_10",
        "cycle_norm",
    ]

    train_features = make_lag_features(history_df, target_col).dropna(
        subset=feature_columns + [target_col]
    )

    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=3,
        random_state=random_state,
    )
    model.fit(train_features[feature_columns], train_features[target_col])

    for _, test_row in test_df.iterrows():
        next_row = test_row.copy()
        next_row[target_col] = np.nan

        temp_df = pd.concat(
            [history_df, pd.DataFrame([next_row])],
            ignore_index=True,
        )
        next_features = make_lag_features(temp_df, target_col).iloc[[-1]][
            feature_columns
        ]

        prediction = max(float(model.predict(next_features)[0]), 0.0)
        predictions.append(prediction)

        next_row[target_col] = prediction
        history_df = pd.concat(
            [history_df, pd.DataFrame([next_row])],
            ignore_index=True,
        )

    return np.array(predictions)


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    denominator = np.abs(y_true) + np.abs(y_pred)
    smape = np.mean(
        np.where(
            denominator == 0,
            0,
            2 * np.abs(y_pred - y_true) / denominator,
        )
    )

    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "smape": float(smape),
    }


def run_final_forecast(
    series_df: pd.DataFrame,
    scenarios: pd.DataFrame,
    config: EvaluationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    initial_capacity = float(series_df["initial_capacity"].dropna().iloc[0])

    forecast_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []

    for _, scenario in scenarios.iterrows():
        scenario_id = scenario["scenario_id"]
        forecast_origin = int(scenario["forecast_origin"])
        horizon = int(scenario["horizon"])

        train_df = (
            series_df[series_df["cycle"] <= forecast_origin]
            .copy()
            .reset_index(drop=True)
        )
        test_df = (
            series_df[
                (series_df["cycle"] > forecast_origin)
                & (series_df["cycle"] <= forecast_origin + horizon)
            ]
            .copy()
            .reset_index(drop=True)
        )

        if len(test_df) != horizon:
            raise ValueError(
                f"{scenario_id} expected horizon {horizon}, "
                f"got {len(test_df)} test rows"
            )

        y_pred_capacity = recursive_random_forest_forecast(
            train_df=train_df,
            test_df=test_df,
            target_col=config.target_col,
            random_state=config.random_state,
        )
        y_true_capacity = test_df["capacity_ah"].to_numpy()
        y_true_soh = test_df["soh"].to_numpy()
        y_pred_soh = y_pred_capacity / initial_capacity
        metrics = calculate_metrics(y_true_capacity, y_pred_capacity)

        metric_rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario["scenario_type"],
                "target_name": config.target_name,
                "model_family": config.model_family,
                "model_name": config.model_name,
                "forecast_origin": forecast_origin,
                "horizon": horizon,
                "capacity_mae": metrics["mae"],
                "capacity_rmse": metrics["rmse"],
                "capacity_smape": metrics["smape"],
                "includes_eol": bool(scenario["includes_eol"]),
                "true_eol_cycle": int(scenario["true_eol_cycle"]),
                "true_rul": int(scenario["true_rul"]),
            }
        )

        for row_idx, test_row in test_df.iterrows():
            forecast_rows.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_type": scenario["scenario_type"],
                    "cell_id": test_row["cell_id"],
                    "target_name": config.target_name,
                    "model_family": config.model_family,
                    "model_name": config.model_name,
                    "forecast_origin": forecast_origin,
                    "horizon": horizon,
                    "cycle": int(test_row["cycle"]),
                    "step": row_idx + 1,
                    "y_true_capacity": float(y_true_capacity[row_idx]),
                    "y_pred_capacity": float(y_pred_capacity[row_idx]),
                    "y_true_soh": float(y_true_soh[row_idx]),
                    "y_pred_soh": float(y_pred_soh[row_idx]),
                    "true_eol_cycle": int(scenario["true_eol_cycle"]),
                    "true_rul": int(scenario["true_rul"]),
                    "includes_eol": bool(scenario["includes_eol"]),
                }
            )

    return pd.DataFrame(forecast_rows), pd.DataFrame(metric_rows)


def get_risk_level(soh_value: float, eol_threshold: float) -> str:
    if soh_value < eol_threshold:
        return "critical"
    if soh_value < 0.90:
        return "warning"
    return "normal"


def find_sustained_eol_cycle(
    forecast_df: pd.DataFrame,
    soh_col: str,
    threshold: float,
    confirmation_cycles: int,
) -> float:
    ordered_df = forecast_df.sort_values("cycle").reset_index(drop=True)
    below_threshold = (ordered_df[soh_col] < threshold).to_numpy()
    cycles = ordered_df["cycle"].to_numpy()

    for start_idx in range(0, len(ordered_df) - confirmation_cycles + 1):
        window = below_threshold[start_idx : start_idx + confirmation_cycles]

        if window.all():
            return float(cycles[start_idx])

    return np.nan


def evaluate_rul_decisions(
    forecasts: pd.DataFrame,
    series_df: pd.DataFrame,
    config: EvaluationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    initial_threshold = float(series_df["eol_threshold"].dropna().iloc[0])
    confirmation_cycles = int(
        series_df["eol_confirmation_cycles"].dropna().iloc[0]
    )

    prediction_rows: list[dict[str, object]] = []

    group_columns = [
        "scenario_id",
        "scenario_type",
        "target_name",
        "model_name",
    ]

    for keys, group in forecasts.groupby(group_columns):
        scenario_id, scenario_type, target_name, model_name = keys
        group = group.sort_values("cycle").reset_index(drop=True)

        forecast_origin = int(group["forecast_origin"].iloc[0])
        horizon = int(group["horizon"].iloc[0])
        forecast_end_cycle = int(group["cycle"].max())
        true_eol_cycle = int(group["true_eol_cycle"].iloc[0])
        true_rul = int(group["true_rul"].iloc[0])
        true_event_in_horizon = bool(group["includes_eol"].iloc[0])

        origin_row = series_df[series_df["cycle"] == forecast_origin].iloc[0]
        origin_soh = float(origin_row["soh"])
        origin_below_threshold = bool(origin_soh < initial_threshold)

        predicted_eol_cycle = find_sustained_eol_cycle(
            forecast_df=group,
            soh_col="y_pred_soh",
            threshold=initial_threshold,
            confirmation_cycles=confirmation_cycles,
        )
        is_censored = pd.isna(predicted_eol_cycle)

        if is_censored:
            predicted_rul = np.nan
            eol_cycle_error = np.nan
            rul_error = np.nan
            abs_rul_error = np.nan
        else:
            predicted_rul = int(predicted_eol_cycle - forecast_origin)
            eol_cycle_error = int(predicted_eol_cycle - true_eol_cycle)
            rul_error = int(predicted_rul - true_rul)
            abs_rul_error = abs(rul_error)

        predicted_event = not is_censored

        if true_event_in_horizon and predicted_event:
            event_status = "true_positive"
        elif true_event_in_horizon and not predicted_event:
            event_status = "false_negative"
        elif not true_event_in_horizon and predicted_event:
            event_status = "false_positive"
        else:
            event_status = "true_negative"

        prediction_rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "cell_id": group["cell_id"].iloc[0],
                "target_name": target_name,
                "model_family": config.model_family,
                "model_name": model_name,
                "forecast_origin": forecast_origin,
                "origin_soh": origin_soh,
                "origin_risk_level": get_risk_level(
                    origin_soh, initial_threshold
                ),
                "origin_below_threshold": origin_below_threshold,
                "horizon": horizon,
                "forecast_end_cycle": forecast_end_cycle,
                "true_eol_cycle": true_eol_cycle,
                "true_rul": true_rul,
                "true_event_in_horizon": true_event_in_horizon,
                "predicted_eol_cycle": predicted_eol_cycle,
                "predicted_rul": predicted_rul,
                "is_censored": is_censored,
                "event_status": event_status,
                "eol_cycle_error": eol_cycle_error,
                "rul_error": rul_error,
                "abs_rul_error": abs_rul_error,
            }
        )

    predictions = pd.DataFrame(prediction_rows)
    metrics = summarize_rul_metrics(predictions, config)

    return predictions, metrics


def summarize_rul_metrics(
    predictions: pd.DataFrame,
    config: EvaluationConfig,
) -> pd.DataFrame:
    metric_rows: list[dict[str, object]] = []

    for model_name, group in predictions.groupby("model_name"):
        true_positive = int((group["event_status"] == "true_positive").sum())
        false_negative = int(
            (group["event_status"] == "false_negative").sum()
        )
        false_positive = int(
            (group["event_status"] == "false_positive").sum()
        )
        true_negative = int((group["event_status"] == "true_negative").sum())

        precision_denominator = true_positive + false_positive
        detection_denominator = true_positive + false_negative
        specificity_denominator = true_negative + false_positive

        detected = group[group["event_status"] == "true_positive"]

        metric_rows.append(
            {
                "target_name": config.target_name,
                "model_family": config.model_family,
                "model_name": model_name,
                "true_positive": true_positive,
                "false_negative": false_negative,
                "false_positive": false_positive,
                "true_negative": true_negative,
                "precision": (
                    true_positive / precision_denominator
                    if precision_denominator
                    else np.nan
                ),
                "eol_detection_rate": (
                    true_positive / detection_denominator
                    if detection_denominator
                    else np.nan
                ),
                "specificity": (
                    true_negative / specificity_denominator
                    if specificity_denominator
                    else np.nan
                ),
                "false_alarm_rate": (
                    false_positive / specificity_denominator
                    if specificity_denominator
                    else np.nan
                ),
                "rul_detected_count": len(detected),
                "rul_mae_detected": (
                    float(detected["abs_rul_error"].mean())
                    if len(detected)
                    else np.nan
                ),
                "rul_rmse_detected": (
                    float(np.sqrt(np.mean(detected["rul_error"] ** 2)))
                    if len(detected)
                    else np.nan
                ),
                "rul_bias_detected": (
                    float(detected["rul_error"].mean())
                    if len(detected)
                    else np.nan
                ),
                "early_warning_count": int(
                    (detected["rul_error"] < 0).sum()
                ),
                "late_warning_count": int((detected["rul_error"] > 0).sum()),
                "exact_warning_count": int(
                    (detected["rul_error"] == 0).sum()
                ),
            }
        )

    return pd.DataFrame(metric_rows)


def build_final_artifacts(
    project_root: Path,
    config: EvaluationConfig | None = None,
) -> dict[str, pd.DataFrame]:
    config = config or EvaluationConfig()
    paths = default_paths(project_root)
    paths.csv_output_dir.mkdir(parents=True, exist_ok=True)
    paths.parquet_output_dir.mkdir(parents=True, exist_ok=True)

    series_df = load_modeling_series(paths)
    scenarios = load_rolling_scenarios(paths)

    forecasts, forecast_metrics = run_final_forecast(
        series_df=series_df,
        scenarios=scenarios,
        config=config,
    )
    rul_predictions, rul_metrics = evaluate_rul_decisions(
        forecasts=forecasts,
        series_df=series_df,
        config=config,
    )

    leaderboard = (
        forecast_metrics.groupby(
            ["scenario_type", "target_name", "model_family", "model_name"],
            as_index=False,
        )
        .agg(
            scenario_count=("scenario_id", "nunique"),
            capacity_mae=("capacity_mae", "mean"),
            capacity_rmse=("capacity_rmse", "mean"),
            capacity_smape=("capacity_smape", "mean"),
        )
        .sort_values(["scenario_type", "capacity_mae"])
        .reset_index(drop=True)
    )

    decision_leaderboard = rul_metrics.sort_values(
        ["eol_detection_rate", "false_alarm_rate", "rul_mae_detected"],
        ascending=[False, True, True],
        na_position="last",
    ).reset_index(drop=True)

    forecasts.to_csv(paths.csv_output_dir / "final_rf_forecasts.csv", index=False)
    forecast_metrics.to_csv(
        paths.csv_output_dir / "final_rf_forecast_metrics.csv",
        index=False,
    )
    leaderboard.to_csv(
        paths.csv_output_dir / "final_rf_forecast_leaderboard.csv",
        index=False,
    )
    rul_predictions.to_csv(
        paths.csv_output_dir / "final_rf_rul_predictions.csv",
        index=False,
    )
    rul_metrics.to_csv(
        paths.csv_output_dir / "final_rf_rul_metrics.csv",
        index=False,
    )
    decision_leaderboard.to_csv(
        paths.csv_output_dir / "final_rf_decision_leaderboard.csv",
        index=False,
    )

    forecasts.to_parquet(
        paths.parquet_output_dir / "final_rf_forecasts.parquet",
        index=False,
    )
    rul_predictions.to_parquet(
        paths.parquet_output_dir / "final_rf_rul_predictions.parquet",
        index=False,
    )

    return {
        "series": series_df,
        "scenarios": scenarios,
        "forecasts": forecasts,
        "forecast_metrics": forecast_metrics,
        "forecast_leaderboard": leaderboard,
        "rul_predictions": rul_predictions,
        "rul_metrics": rul_metrics,
        "decision_leaderboard": decision_leaderboard,
    }

