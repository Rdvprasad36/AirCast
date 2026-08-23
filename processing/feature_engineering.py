"""
processing/feature_engineering.py — Feature engineering for ML models.

Takes raw AQI + traffic readings from the DB and produces a unified
DataFrame with:
  - Temporal features  (hour, day-of-week, is_weekend, is_peak_hour)
  - Lag features       (aqi_lag_1h, aqi_lag_3h, aqi_lag_6h, aqi_lag_24h)
  - Rolling statistics (aqi_roll_mean_3h, aqi_roll_std_3h)
  - Pollutant features (pm25, pm10, no2, o3, so2, co)
  - Weather features   (humidity, temperature, wind_speed)
  - Traffic features   (congestion_index, current_speed, incident_count)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select, and_

from ingestion.database import AQIReading, TrafficReading, AsyncSessionLocal

logger = logging.getLogger(__name__)

# Hours considered "peak" traffic
PEAK_HOURS = list(range(8, 11)) + list(range(17, 21))


def build_feature_dataframe(
    aqi_df: pd.DataFrame,
    traffic_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge AQI + traffic DataFrames (both must have a 'timestamp' column)
    and engineer all ML features.

    Parameters
    ----------
    aqi_df     : DataFrame of AQIReading rows, indexed/sorted by timestamp
    traffic_df : DataFrame of TrafficReading rows, indexed/sorted by timestamp

    Returns
    -------
    feature_df : Ready-to-use ML DataFrame (no NaN in key columns)
    """
    if aqi_df.empty:
        raise ValueError("aqi_df is empty — need at least 25 hours of data.")

    # ── Timestamp alignment ─────────────────────────────────────────
    # Round both to nearest 5-minute bucket, then merge-asof
    aqi_df = aqi_df.copy()
    traffic_df = traffic_df.copy()

    aqi_df["timestamp"] = pd.to_datetime(aqi_df["timestamp"])
    aqi_df = aqi_df.sort_values("timestamp").set_index("timestamp")

    if not traffic_df.empty:
        traffic_df["timestamp"] = pd.to_datetime(traffic_df["timestamp"])
        traffic_df = traffic_df.sort_values("timestamp").set_index("timestamp")

        # Merge: for each AQI timestamp, find nearest traffic reading ≤5 min away
        merged = pd.merge_asof(
            aqi_df.reset_index(),
            traffic_df[["congestion_index", "current_speed", "incident_count"]].reset_index(),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("10min"),
        )
    else:
        merged = aqi_df.reset_index()
        merged["congestion_index"] = 0.3
        merged["current_speed"] = 40.0
        merged["incident_count"] = 0

    df = merged.set_index("timestamp").sort_index()

    # ── Temporal features ───────────────────────────────────────────
    df["hour"] = df.index.hour
    df["day_of_week"] = df.index.dayofweek   # 0=Monday
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_peak_hour"] = df["hour"].isin(PEAK_HOURS).astype(int)
    df["month"] = df.index.month

    # ── Lag features ────────────────────────────────────────────────
    # Resample to hourly to create clean lags
    hourly = df["aqi"].resample("1h").mean().ffill()
    df["aqi_lag_1h"] = df["aqi"].shift(freq="1h").reindex(df.index, method="nearest", tolerance=pd.Timedelta("30min"))
    df["aqi_lag_3h"] = hourly.reindex(df.index, method="nearest").shift(freq="3h").reindex(df.index, method="nearest")
    df["aqi_lag_6h"] = hourly.reindex(df.index, method="nearest").shift(freq="6h").reindex(df.index, method="nearest")
    df["aqi_lag_24h"] = hourly.reindex(df.index, method="nearest").shift(freq="24h").reindex(df.index, method="nearest")

    # ── Rolling statistics (3-hour window) ──────────────────────────
    df["aqi_roll_mean_3h"] = df["aqi"].rolling("3h").mean()
    df["aqi_roll_std_3h"] = df["aqi"].rolling("3h").std().fillna(0)
    df["aqi_roll_max_6h"] = df["aqi"].rolling("6h").max()

    # ── Target variable ─────────────────────────────────────────────
    df["aqi_next_1h"] = hourly.reindex(df.index, method="nearest").shift(freq="-1h").reindex(df.index, method="nearest")

    # ── Pollutant features ──────────────────────────────────────────
    for col in ["pm25", "pm10", "no2", "o3", "so2", "co",
                "humidity", "temperature", "wind_speed"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = df[col].ffill().bfill()

    # Fill remaining NaNs
    df = df.ffill().bfill()

    logger.info(
        "Feature engineering complete: %d rows, %d columns",
        len(df), len(df.columns),
    )
    return df


def get_feature_columns() -> list[str]:
    """Return the ordered list of feature columns used by ML models."""
    return [
        "hour", "day_of_week", "is_weekend", "is_peak_hour", "month",
        "aqi_lag_1h", "aqi_lag_3h", "aqi_lag_6h", "aqi_lag_24h",
        "aqi_roll_mean_3h", "aqi_roll_std_3h", "aqi_roll_max_6h",
        "pm25", "pm10", "no2", "o3", "so2", "co",
        "humidity", "temperature", "wind_speed",
        "congestion_index", "current_speed", "incident_count",
    ]


async def load_training_data(hours_back: int = 720) -> pd.DataFrame:
    """
    Load recent AQI + traffic readings from DB and return feature DataFrame.
    Default: last 30 days (720 hours).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    async with AsyncSessionLocal() as db:
        aqi_rows = (
            await db.execute(
                select(AQIReading).where(AQIReading.timestamp >= cutoff).order_by(AQIReading.timestamp)
            )
        ).scalars().all()

        traffic_rows = (
            await db.execute(
                select(TrafficReading).where(TrafficReading.timestamp >= cutoff).order_by(TrafficReading.timestamp)
            )
        ).scalars().all()

    aqi_df = pd.DataFrame([r.to_dict() for r in aqi_rows]) if aqi_rows else pd.DataFrame()
    traffic_df = pd.DataFrame([r.to_dict() for r in traffic_rows]) if traffic_rows else pd.DataFrame()

    if aqi_df.empty:
        logger.warning("No AQI data found in the last %d hours.", hours_back)
        return pd.DataFrame()

    return build_feature_dataframe(aqi_df, traffic_df)
