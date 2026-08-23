"""
api/routes/live.py — Live data endpoints.

GET /api/live/aqi     → Latest AQI reading + category + anomaly flag
GET /api/live/traffic → Latest traffic reading + congestion level
GET /api/live/stats   → Correlation summary (traffic vs AQI)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from ingestion.database import (
    AQIReading, TrafficReading,
    get_latest_aqi, get_latest_traffic, get_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _congestion_label(ci: float) -> str:
    if ci < 0.2:
        return "Free Flow"
    elif ci < 0.4:
        return "Light"
    elif ci < 0.6:
        return "Moderate"
    elif ci < 0.8:
        return "Heavy"
    else:
        return "Standstill"


@router.get("/aqi")
async def get_live_aqi(db: AsyncSession = Depends(get_session)):
    """Return the most recent AQI reading."""
    reading = await get_latest_aqi(db)
    if reading is None:
        raise HTTPException(status_code=503, detail="No AQI data available yet.")

    category, color = settings.aqi_category(reading.aqi)
    return {
        "aqi": reading.aqi,
        "category": category,
        "color": color,
        "is_anomaly": reading.is_anomaly,
        "source": reading.source,
        "pollutants": {
            "pm25": reading.pm25,
            "pm10": reading.pm10,
            "no2": reading.no2,
            "o3": reading.o3,
            "so2": reading.so2,
            "co": reading.co,
        },
        "weather": {
            "humidity": reading.humidity,
            "temperature": reading.temperature,
            "wind_speed": reading.wind_speed,
        },
        "timestamp": reading.timestamp.isoformat(),
    }


@router.get("/traffic")
async def get_live_traffic(db: AsyncSession = Depends(get_session)):
    """Return the most recent traffic reading."""
    reading = await get_latest_traffic(db)
    if reading is None:
        raise HTTPException(status_code=503, detail="No traffic data available yet.")

    return {
        "congestion_index": reading.congestion_index,
        "congestion_label": _congestion_label(reading.congestion_index),
        "current_speed_kmh": reading.current_speed,
        "free_flow_speed_kmh": reading.free_flow_speed,
        "delay_factor": (
            reading.current_travel_time / reading.free_flow_travel_time
            if reading.free_flow_travel_time > 0 else 1.0
        ),
        "road_closure": reading.road_closure,
        "incident_count": reading.incident_count,
        "timestamp": reading.timestamp.isoformat(),
    }


@router.get("/stats")
async def get_correlation_stats(
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
):
    """
    Return correlation statistics between traffic congestion and AQI
    over the last N hours. Useful for the dashboard summary cards.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

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
        return {"correlation": None, "message": "Not enough data yet."}

    aqi_df = pd.DataFrame([r.to_dict() for r in aqi_rows])
    aqi_df["timestamp"] = pd.to_datetime(aqi_df["timestamp"])

    stats: dict = {
        "period_hours": hours,
        "aqi_mean": round(float(aqi_df["aqi"].mean()), 1),
        "aqi_max": round(float(aqi_df["aqi"].max()), 1),
        "aqi_min": round(float(aqi_df["aqi"].min()), 1),
        "anomaly_count": int(aqi_df["is_anomaly"].sum()),
        "reading_count": len(aqi_df),
    }

    if traffic_rows:
        traffic_df = pd.DataFrame([r.to_dict() for r in traffic_rows])
        traffic_df["timestamp"] = pd.to_datetime(traffic_df["timestamp"])

        # Merge on nearest timestamp
        merged = pd.merge_asof(
            aqi_df.sort_values("timestamp"),
            traffic_df[["timestamp", "congestion_index"]].sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("15min"),
        )
        if "congestion_index_y" in merged.columns and len(merged.dropna()) > 5:
            corr = merged["aqi"].corr(merged["congestion_index_y"])
            stats["traffic_aqi_correlation"] = round(float(corr), 3)
            stats["congestion_mean"] = round(float(traffic_df["congestion_index"].mean()), 3)

    return stats
