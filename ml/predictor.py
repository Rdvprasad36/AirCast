"""
ml/predictor.py — Unified AQI prediction interface.

Two models are available:
  1. XGBoost (primary)  — uses full feature set including traffic + weather
  2. Prophet (baseline) — univariate time-series, great for trend explanation

Public API:
  predict_next_hour()   → returns predicted AQI for next 60 minutes
  predict_next_n_hours() → returns list of N hourly predictions
  retrain_models()       → retrain both models from latest DB data
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import joblib
import numpy as np
import pandas as pd

from config import settings
from processing.feature_engineering import (
    get_feature_columns,
    load_training_data,
)

logger = logging.getLogger(__name__)

MODEL_DIR = Path("ml/models")
XGBOOST_PATH = MODEL_DIR / "xgboost_aqi.pkl"
PROPHET_PATH = MODEL_DIR / "prophet_aqi.pkl"


class Prediction(NamedTuple):
    forecast_for: datetime
    predicted_aqi: float
    model_name: str
    confidence_lower: float | None
    confidence_upper: float | None


# ---------------------------------------------------------------------------
# XGBoost Model
# ---------------------------------------------------------------------------

def train_xgboost(df: pd.DataFrame) -> object:
    """Train XGBoost regressor on feature DataFrame."""
    from xgboost import XGBRegressor

    feature_cols = get_feature_columns()
    available = [c for c in feature_cols if c in df.columns]
    target = "aqi_next_1h"

    if target not in df.columns:
        raise ValueError(f"Target column '{target}' missing from DataFrame.")

    X = df[available].dropna()
    y = df.loc[X.index, target].dropna()
    # Align
    idx = X.index.intersection(y.index)
    X, y = X.loc[idx], y.loc[idx]

    if len(X) < 10:
        raise ValueError(f"Not enough training samples: {len(X)}")

    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_cols": available}, XGBOOST_PATH)
    logger.info("XGBoost trained on %d samples, %d features.", len(X), len(available))
    return model


def predict_xgboost(feature_row: dict) -> Prediction:
    """Predict next-hour AQI using XGBoost."""
    if not XGBOOST_PATH.exists():
        raise FileNotFoundError("XGBoost model not trained yet. Run retrain_models() first.")

    bundle = joblib.load(XGBOOST_PATH)
    model = bundle["model"]
    feature_cols = bundle["feature_cols"]

    X = pd.DataFrame([feature_row])[feature_cols].fillna(0)
    pred = float(model.predict(X)[0])

    # Approximate 90% CI via ±15% of predicted value
    return Prediction(
        forecast_for=datetime.now(timezone.utc) + timedelta(hours=1),
        predicted_aqi=max(0, pred),
        model_name="xgboost",
        confidence_lower=max(0, pred * 0.85),
        confidence_upper=pred * 1.15,
    )


# ---------------------------------------------------------------------------
# Prophet Model
# ---------------------------------------------------------------------------

def train_prophet(df: pd.DataFrame) -> object:
    """Train Facebook Prophet on hourly AQI time series."""
    try:
        from prophet import Prophet
    except ImportError:
        logger.warning("Prophet not installed. Skipping Prophet training.")
        return None

    # Prophet expects columns: ds (datetime), y (value)
    prophet_df = df[["aqi"]].copy()
    prophet_df.index = pd.to_datetime(prophet_df.index)
    hourly = prophet_df["aqi"].resample("1h").mean().dropna().reset_index()
    hourly.columns = ["ds", "y"]

    if len(hourly) < 24:
        raise ValueError(f"Need at least 24 hourly data points for Prophet, got {len(hourly)}.")

    # Remove timezone for Prophet compatibility
    hourly["ds"] = hourly["ds"].dt.tz_localize(None)

    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.90,
    )
    model.fit(hourly)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, PROPHET_PATH)
    logger.info("Prophet trained on %d hourly points.", len(hourly))
    return model


def predict_prophet(n_hours: int = 6) -> list[Prediction]:
    """Predict next N hours using Prophet."""
    if not PROPHET_PATH.exists():
        raise FileNotFoundError("Prophet model not trained yet. Run retrain_models() first.")

    model = joblib.load(PROPHET_PATH)
    future = model.make_future_dataframe(periods=n_hours, freq="h", include_history=False)
    forecast = model.predict(future)

    now = datetime.now(timezone.utc)
    results = []
    for i, row in forecast.iterrows():
        results.append(Prediction(
            forecast_for=now + timedelta(hours=i + 1),
            predicted_aqi=max(0, float(row["yhat"])),
            model_name="prophet",
            confidence_lower=max(0, float(row["yhat_lower"])),
            confidence_upper=max(0, float(row["yhat_upper"])),
        ))
    return results


# ---------------------------------------------------------------------------
# Unified Public API
# ---------------------------------------------------------------------------

def _build_current_feature_row(df: pd.DataFrame) -> dict:
    """Extract the most recent row as a feature dict."""
    feature_cols = get_feature_columns()
    row = df.iloc[-1]
    return {col: row.get(col, 0) for col in feature_cols}


def predict_next_hour(df: pd.DataFrame | None = None) -> Prediction:
    """
    Predict next-hour AQI. Uses XGBoost if available, else Prophet,
    else returns a simple moving-average estimate.
    """
    # Try XGBoost first
    if XGBOOST_PATH.exists() and df is not None and not df.empty:
        try:
            feature_row = _build_current_feature_row(df)
            return predict_xgboost(feature_row)
        except Exception as exc:
            logger.warning("XGBoost prediction failed: %s — falling back.", exc)

    # Try Prophet
    if PROPHET_PATH.exists():
        try:
            return predict_prophet(n_hours=1)[0]
        except Exception as exc:
            logger.warning("Prophet prediction failed: %s — falling back.", exc)

    # Moving average fallback
    aqi_val = float(df["aqi"].tail(6).mean()) if df is not None and not df.empty else 80.0
    return Prediction(
        forecast_for=datetime.now(timezone.utc) + timedelta(hours=1),
        predicted_aqi=aqi_val,
        model_name="moving_average",
        confidence_lower=aqi_val * 0.9,
        confidence_upper=aqi_val * 1.1,
    )


def predict_next_n_hours(n: int = 6, df: pd.DataFrame | None = None) -> list[Prediction]:
    """Return predictions for the next N hours."""
    results = []
    if PROPHET_PATH.exists():
        try:
            return predict_prophet(n_hours=n)
        except Exception as exc:
            logger.warning("Multi-hour Prophet prediction failed: %s", exc)

    # Fallback: repeat XGBoost/MA estimate
    base = predict_next_hour(df)
    for i in range(n):
        results.append(Prediction(
            forecast_for=datetime.now(timezone.utc) + timedelta(hours=i + 1),
            predicted_aqi=base.predicted_aqi,
            model_name=base.model_name + "_repeated",
            confidence_lower=base.confidence_lower,
            confidence_upper=base.confidence_upper,
        ))
    return results


def retrain_models() -> None:
    """
    Synchronous wrapper — retrain both models from DB data.
    Called by the scheduler every 6 hours.
    """
    import asyncio

    async def _async_retrain():
        df = await load_training_data(hours_back=720)
        if df.empty:
            logger.warning("No data available for retraining.")
            return
        try:
            train_xgboost(df)
        except Exception as exc:
            logger.error("XGBoost training failed: %s", exc)
        try:
            train_prophet(df)
        except Exception as exc:
            logger.error("Prophet training failed: %s", exc)

        from processing.anomaly_detection import retrain_detector_from_db
        await retrain_detector_from_db()

    asyncio.run(_async_retrain())
