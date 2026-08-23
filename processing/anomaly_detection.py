"""
processing/anomaly_detection.py — IsolationForest-based AQI anomaly detector.

Detects unusual AQI spikes by training on recent historical readings.
Flags the AQI reading in the DB and optionally triggers escalated alerts.

Strategy:
  1. Train IsolationForest on last 7 days of readings (retrained every 6 h).
  2. Score each new reading — if anomaly, mark is_anomaly=True in DB.
  3. Anomalies are surfaced in the dashboard with a warning badge.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import select, update

from config import settings
from ingestion.database import AQIReading, AsyncSessionLocal

logger = logging.getLogger(__name__)

MODEL_PATH = Path("ml/models/anomaly_detector.pkl")
_detector: IsolationForest | None = None


def _load_detector() -> IsolationForest | None:
    """Load persisted detector from disk, return None if missing."""
    global _detector
    if MODEL_PATH.exists():
        _detector = joblib.load(MODEL_PATH)
        logger.info("Anomaly detector loaded from %s", MODEL_PATH)
    return _detector


def _save_detector(model: IsolationForest) -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)


def train_anomaly_detector(df: pd.DataFrame) -> IsolationForest:
    """
    Train IsolationForest on AQI + pollutant features.
    Returns the fitted model (also saves to disk).
    """
    features = ["aqi", "pm25", "pm10", "no2", "humidity", "temperature"]
    available = [f for f in features if f in df.columns]
    X = df[available].fillna(df[available].median())

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,   # expect ~5% anomalies
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)
    _save_detector(model)
    logger.info("Anomaly detector trained on %d samples.", len(X))
    return model


def is_anomaly(reading: AQIReading) -> bool:
    """
    Score a single reading. Returns True if anomaly.
    Falls back to simple threshold rule if no model exists.
    """
    global _detector
    if _detector is None:
        _detector = _load_detector()

    if _detector is None:
        # No model yet — simple rule: AQI jump > 75 from recent mean
        return reading.aqi > 300

    X = np.array([[
        reading.aqi or 0,
        reading.pm25 or 0,
        reading.pm10 or 0,
        reading.no2 or 0,
        reading.humidity or 50,
        reading.temperature or 25,
    ]])

    score = _detector.predict(X)  # -1 = anomaly, 1 = normal
    return bool(score[0] == -1)


async def flag_anomaly_if_needed(reading: AQIReading) -> bool:
    """
    Evaluate the reading, flag it in DB if anomalous.
    Returns True if an anomaly was detected.
    """
    detected = is_anomaly(reading)
    if detected:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(AQIReading)
                .where(AQIReading.id == reading.id)
                .values(is_anomaly=True)
            )
            await db.commit()
        logger.warning(
            "🚨 ANOMALY detected — id=%d aqi=%.1f pm25=%s",
            reading.id, reading.aqi, reading.pm25,
        )
    return detected


async def retrain_detector_from_db() -> None:
    """Load last 7 days from DB and retrain the detector."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(AQIReading)
                .where(AQIReading.timestamp >= cutoff)
                .order_by(AQIReading.timestamp)
            )
        ).scalars().all()

    if len(rows) < 20:
        logger.info("Not enough data to retrain anomaly detector (%d rows).", len(rows))
        return

    df = pd.DataFrame([r.to_dict() for r in rows])
    global _detector
    _detector = train_anomaly_detector(df)
