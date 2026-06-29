from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Battery Predictive Maintenance",
    layout="wide",
)


def find_project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in current.parents:
        if (parent / "data").exists() and (parent / "outputs").exists():
            return parent

    raise FileNotFoundError("Battery_TimeSeries_Analysis project root not found.")


PROJECT_ROOT = find_project_root()

LABELED_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "paraquet"
    / "battery_cycles_labeled.parquet"
)
FORECAST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "csv"
    / "evaluation"
    / "final"
    / "final_rf_forecasts.csv"
)
RUL_PREDICTION_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "csv"
    / "evaluation"
    / "final"
    / "final_rf_rul_predictions.csv"
)
DECISION_LEADERBOARD_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "csv"
    / "evaluation"
    / "final"
    / "final_rf_decision_leaderboard.csv"
)


@st.cache_data
def load_artifacts() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cycles = pd.read_parquet(LABELED_DATA_PATH)
    forecasts = pd.read_csv(FORECAST_PATH)
    rul_predictions = pd.read_csv(RUL_PREDICTION_PATH)
    decision_leaderboard = pd.read_csv(DECISION_LEADERBOARD_PATH)

    cycles = cycles.sort_values("cycle").reset_index(drop=True)
    forecasts = forecasts.sort_values(
        ["scenario_id", "model_name", "cycle"]
    ).reset_index(drop=True)
    rul_predictions = rul_predictions.sort_values(
        ["scenario_type", "forecast_origin", "horizon", "scenario_id"]
    ).reset_index(drop=True)

    return cycles, forecasts, rul_predictions, decision_leaderboard


def format_percent(value: float | int | None) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def format_cycle(value: float | int | None) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{int(value)}"


def format_rul(value: float | int | None) -> str:
    if pd.isna(value):
        return "Censored"
    return f"{int(value)} cycles"


def make_scenario_label(row: pd.Series) -> str:
    status = row["event_status"].replace("_", " ")
    return (
        f"{row['scenario_id']} | origin {int(row['forecast_origin'])} "
        f"| {status}"
    )


def risk_badge_color(risk_level: str) -> str:
    if risk_level == "critical":
        return "#b42318"
    if risk_level == "warning":
        return "#b54708"
    return "#027a48"


def plot_history(
    cycles: pd.DataFrame,
    selected_cell: str,
    threshold_capacity: float,
    true_eol_cycle: int,
) -> plt.Figure:
    modeling_cycles = cycles[
        (cycles["cell_id"] == selected_cell) & cycles["is_modeling_cycle"]
    ].copy()

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(
        modeling_cycles["cycle"],
        modeling_cycles["capacity_ah"],
        color="#344054",
        linewidth=1.3,
        label="Observed capacity",
    )
    ax.axhline(
        threshold_capacity,
        color="#d92d20",
        linestyle="--",
        linewidth=1.2,
        label="80% EOL threshold",
    )
    ax.axvline(
        true_eol_cycle,
        color="#101828",
        linestyle=":",
        linewidth=1.4,
        label="True sustained EOL",
    )
    ax.set_title(f"{selected_cell} Capacity Fade")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity (Ah)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right")
    return fig


def plot_forecast(
    cycles: pd.DataFrame,
    forecast_df: pd.DataFrame,
    selected_prediction: pd.Series,
    history_window: int,
    threshold_capacity: float,
) -> plt.Figure:
    forecast_origin = int(selected_prediction["forecast_origin"])
    true_eol_cycle = int(selected_prediction["true_eol_cycle"])
    predicted_eol_cycle = selected_prediction["predicted_eol_cycle"]

    history_df = (
        cycles[
            (cycles["is_modeling_cycle"])
            & (cycles["cycle"] <= forecast_origin)
        ]
        .tail(history_window)
        .copy()
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        history_df["cycle"],
        history_df["capacity_ah"],
        color="#667085",
        linewidth=1.4,
        label="Train history",
    )
    ax.plot(
        forecast_df["cycle"],
        forecast_df["y_true_capacity"],
        color="#101828",
        linewidth=2.2,
        label="Actual future",
    )
    ax.plot(
        forecast_df["cycle"],
        forecast_df["y_pred_capacity"],
        color="#1570ef",
        linewidth=2.2,
        label="RandomForest forecast",
    )
    ax.axhline(
        threshold_capacity,
        color="#d92d20",
        linestyle="--",
        linewidth=1.2,
        label="80% EOL threshold",
    )
    ax.axvline(
        forecast_origin,
        color="#667085",
        linestyle="--",
        linewidth=1.2,
        label="Forecast origin",
    )
    ax.axvline(
        true_eol_cycle,
        color="#101828",
        linestyle=":",
        linewidth=1.5,
        label="True sustained EOL",
    )

    if not pd.isna(predicted_eol_cycle):
        ax.axvline(
            int(predicted_eol_cycle),
            color="#1570ef",
            linestyle=":",
            linewidth=1.5,
            label="Predicted EOL",
        )

    ax.set_title(
        f"{selected_prediction['scenario_id']} Forecast "
        f"(origin {forecast_origin})"
    )
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity (Ah)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    return fig


try:
    cycles_df, forecasts_df, rul_df, decision_df = load_artifacts()
except FileNotFoundError as exc:
    st.error(f"Required artifact was not found: {exc}")
    st.stop()


modeling_cycles_df = cycles_df[cycles_df["is_modeling_cycle"]].copy()
cell_ids = sorted(modeling_cycles_df["cell_id"].unique())

st.title("Battery Predictive Maintenance Dashboard")

st.sidebar.header("Controls")
selected_cell = st.sidebar.selectbox("Cell ID", cell_ids)

cell_cycles_df = modeling_cycles_df[
    modeling_cycles_df["cell_id"] == selected_cell
].copy()

cell_rul_df = rul_df[rul_df["cell_id"] == selected_cell].copy()
cell_forecasts_df = forecasts_df[forecasts_df["cell_id"] == selected_cell].copy()

scenario_labels = {
    make_scenario_label(row): row["scenario_id"]
    for _, row in cell_rul_df.iterrows()
}

default_label = next(
    (
        label
        for label, scenario_id in scenario_labels.items()
        if scenario_id == "eol_o526_lead20_h24"
    ),
    next(iter(scenario_labels)),
)

selected_label = st.sidebar.selectbox(
    "Scenario",
    list(scenario_labels.keys()),
    index=list(scenario_labels.keys()).index(default_label),
)
selected_scenario_id = scenario_labels[selected_label]

history_window = st.sidebar.slider(
    "Train history window",
    min_value=20,
    max_value=160,
    value=60,
    step=10,
)

selected_prediction = cell_rul_df[
    cell_rul_df["scenario_id"] == selected_scenario_id
].iloc[0]
selected_forecast_df = cell_forecasts_df[
    cell_forecasts_df["scenario_id"] == selected_scenario_id
].copy()

initial_capacity = float(cell_cycles_df["initial_capacity"].dropna().iloc[0])
eol_threshold = float(cell_cycles_df["eol_threshold"].dropna().iloc[0])
threshold_capacity = initial_capacity * eol_threshold
true_eol_cycle = int(cell_cycles_df["eol_cycle"].dropna().iloc[0])
latest_cycle = int(cell_cycles_df["cycle"].max())
latest_soh = float(cell_cycles_df.sort_values("cycle")["soh"].iloc[-1])

decision_row = decision_df.iloc[0]

metric_cols = st.columns(6)
metric_cols[0].metric("Cell", selected_cell)
metric_cols[1].metric("Latest Cycle", f"{latest_cycle}")
metric_cols[2].metric("Latest SoH", format_percent(latest_soh))
metric_cols[3].metric("True EOL", format_cycle(true_eol_cycle))
metric_cols[4].metric(
    "Predicted RUL",
    format_rul(selected_prediction["predicted_rul"]),
)
metric_cols[5].metric(
    "EOL Detection",
    format_percent(decision_row["eol_detection_rate"]),
)

status_color = risk_badge_color(selected_prediction["origin_risk_level"])
st.markdown(
    f"""
    <div style="border-left: 5px solid {status_color}; padding: 0.6rem 0 0.6rem 0.8rem; margin: 0.5rem 0 1rem 0;">
        <strong>Selected scenario:</strong> {selected_prediction['scenario_id']}
        &nbsp;&nbsp; <strong>Origin SoH:</strong> {format_percent(selected_prediction['origin_soh'])}
        &nbsp;&nbsp; <strong>Risk:</strong> {selected_prediction['origin_risk_level']}
        &nbsp;&nbsp; <strong>Event:</strong> {selected_prediction['event_status'].replace('_', ' ')}
    </div>
    """,
    unsafe_allow_html=True,
)

tab_overview, tab_forecast, tab_decision = st.tabs(
    ["Overview", "Forecast", "Decision Tables"]
)

with tab_overview:
    st.subheader("Capacity and SoH History")
    st.pyplot(
        plot_history(
            cycles=cycles_df,
            selected_cell=selected_cell,
            threshold_capacity=threshold_capacity,
            true_eol_cycle=true_eol_cycle,
        ),
        clear_figure=True,
    )

    soh_plot_df = cell_cycles_df[
        ["cycle", "capacity_ah", "soh", "rul_clipped", "cycle_type"]
    ].copy()
    soh_plot_df = soh_plot_df.rename(
        columns={
            "cycle": "Cycle",
            "capacity_ah": "Capacity (Ah)",
            "soh": "SoH",
            "rul_clipped": "RUL Clipped",
            "cycle_type": "Cycle Type",
        }
    )
    st.dataframe(
        soh_plot_df.tail(20),
        width="stretch",
        hide_index=True,
    )

with tab_forecast:
    st.subheader("Rolling Forecast Viewer")
    st.pyplot(
        plot_forecast(
            cycles=cell_cycles_df,
            forecast_df=selected_forecast_df,
            selected_prediction=selected_prediction,
            history_window=history_window,
            threshold_capacity=threshold_capacity,
        ),
        clear_figure=True,
    )

    detail_cols = st.columns(5)
    detail_cols[0].metric(
        "Forecast Origin",
        format_cycle(selected_prediction["forecast_origin"]),
    )
    detail_cols[1].metric(
        "Forecast End",
        format_cycle(selected_prediction["forecast_end_cycle"]),
    )
    detail_cols[2].metric(
        "True RUL",
        format_rul(selected_prediction["true_rul"]),
    )
    detail_cols[3].metric(
        "Predicted EOL",
        format_cycle(selected_prediction["predicted_eol_cycle"]),
    )
    detail_cols[4].metric(
        "RUL Error",
        format_rul(selected_prediction["rul_error"]),
    )

    forecast_table = selected_forecast_df[
        [
            "cycle",
            "y_true_capacity",
            "y_pred_capacity",
            "y_true_soh",
            "y_pred_soh",
        ]
    ].rename(
        columns={
            "cycle": "Cycle",
            "y_true_capacity": "Actual Capacity",
            "y_pred_capacity": "Predicted Capacity",
            "y_true_soh": "Actual SoH",
            "y_pred_soh": "Predicted SoH",
        }
    )
    st.dataframe(
        forecast_table,
        width="stretch",
        hide_index=True,
    )

with tab_decision:
    st.subheader("RUL Decision Table")
    decision_table = cell_rul_df[
        [
            "scenario_id",
            "scenario_type",
            "forecast_origin",
            "origin_soh",
            "origin_risk_level",
            "true_rul",
            "predicted_rul",
            "event_status",
            "rul_error",
            "abs_rul_error",
        ]
    ].rename(
        columns={
            "scenario_id": "Scenario",
            "scenario_type": "Scenario Type",
            "forecast_origin": "Forecast Origin",
            "origin_soh": "Origin SoH",
            "origin_risk_level": "Risk",
            "true_rul": "True RUL",
            "predicted_rul": "Predicted RUL",
            "event_status": "Event Status",
            "rul_error": "RUL Error",
            "abs_rul_error": "Abs RUL Error",
        }
    )
    st.dataframe(
        decision_table,
        width="stretch",
        hide_index=True,
    )

    st.subheader("Decision Leaderboard")
    leaderboard_table = decision_df.rename(
        columns={
            "target_name": "Target",
            "model_family": "Model Family",
            "model_name": "Model",
            "true_positive": "TP",
            "false_negative": "FN",
            "false_positive": "FP",
            "true_negative": "TN",
            "eol_detection_rate": "EOL Detection Rate",
            "false_alarm_rate": "False Alarm Rate",
            "rul_mae_detected": "RUL MAE",
            "rul_bias_detected": "RUL Bias",
        }
    )
    st.dataframe(
        leaderboard_table,
        width="stretch",
        hide_index=True,
    )
