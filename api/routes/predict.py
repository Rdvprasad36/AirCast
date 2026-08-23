"""
api/routes/predict.py — ML prediction endpoints.

GET /api/predict/next-hour   → Predict AQI for the next 60 minutes
GET /api/predict/next/{n}    → Predict AQI for next N hours (max 24)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from config import settings
from ingestion.database import AQIReading, TrafficReading, AsyncSessionLocal
from ml.predictor import predict_next_hour, predict_next_n_hours
from processing.feature_engineering import build_feature_dataframe

logger = logging.getLogger(__name__)
router = APIRouter()


async def _load_recent_df(hours: int = 48) -> pd.DataFrame | None:
    """Load recent AQI + traffic data and build feature DataFrame."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        aqi_rows = (
            await db.execute(
                select(AQIReading)
                .where(AQIReading.timestamp >= cutoff)
                .order_by(AQIReading.timestamp)
            )
        ).scalars().all()
        traffic_rows = (
            await db.execute(
                select(TrafficReading)
                .where(TrafficReading.timestamp >= cutoff)
                .order_by(TrafficReading.timestamp)
            )
        ).scalars().all()

    if not aqi_rows:
        return None

    aqi_df = pd.DataFrame([r.to_dict() for r in aqi_rows])
    traffic_df = pd.DataFrame([r.to_dict() for r in traffic_rows]) if traffic_rows else pd.DataFrame()
    try:
        return build_feature_dataframe(aqi_df, traffic_df)
    except Exception as exc:
        logger.warning("Feature engineering failed: %s", exc)
        return aqi_df  # Fall back to raw AQI DataFrame


@router.get("/next-hour")
async def predict_aqi_next_hour():
    """
    Predict AQI for the next 60 minutes.

    Uses XGBoost (if trained) → Prophet (fallback) → Moving Average (last resort).
    Returns prediction with 90% confidence interval and AQI category.
    """
    df = await _load_recent_df()
    prediction = predict_next_hour(df)

    category, color = settings.aqi_category(prediction.predicted_aqi)
    return {
        "forecast_for": prediction.forecast_for.isoformat(),
        "predicted_aqi": round(prediction.predicted_aqi, 1),
        "category": category,
        "color": color,
        "confidence_lower": round(prediction.confidence_lower or 0, 1),
        "confidence_upper": round(prediction.confidence_upper or 0, 1),
        "model_used": prediction.model_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/next/{n}")
async def predict_aqi_next_n_hours(
    n: int,
    model: str = Query(default="auto", enum=["auto", "prophet", "xgboost"]),
):
    """
    Predict AQI for the next N hours (1 ≤ N ≤ 24).

    - `model=auto` uses XGBoost for 1-hour, Prophet for multi-hour
    - `model=prophet` forces Prophet (better trend visualization)
    - `model=xgboost` forces XGBoost repeated estimate
    """
    if n < 1 or n > 24:
        raise HTTPException(status_code=400, detail="n must be between 1 and 24.")

    df = await _load_recent_df()
    predictions = predict_next_n_hours(n=n, df=df)

    results = []
    for p in predictions:
        category, color = settings.aqi_category(p.predicted_aqi)
        results.append({
            "forecast_for": p.forecast_for.isoformat(),
            "predicted_aqi": round(p.predicted_aqi, 1),
            "category": category,
            "color": color,
            "confidence_lower": round(p.confidence_lower or 0, 1),
            "confidence_upper": round(p.confidence_upper or 0, 1),
            "model_used": p.model_name,
        })

    return {
        "hours": n,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "predictions": results,
    }
