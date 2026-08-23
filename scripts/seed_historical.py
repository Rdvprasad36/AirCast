"""
scripts/seed_historical.py — Seed the database with synthetic historical data.

Generates 30 days of realistic AQI + traffic readings for Vizag so that:
  - ML models can be trained immediately without waiting for real data
  - Dashboard shows realistic trend charts from day one

AQI patterns modelled:
  - Diurnal cycle: higher at 8-10am and 6-9pm (traffic peak)
  - Day-of-week: weekdays are 15% higher than weekends
  - Random noise: ±10 AQI units
  - Occasional anomaly spikes (5% of readings)
  - Seasonal baseline: monsoon (Jun-Sep) → lower AQI due to rain
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("data", exist_ok=True)

from config import settings
from ingestion.database import AQIReading, TrafficReading, init_db, AsyncSessionLocal

DAYS = 30
INTERVAL_MINUTES = 5
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ── Vizag AQI baseline by hour (0–23) ─────────────────────────────────────
HOURLY_AQI_PROFILE = {
    0: 55, 1: 50, 2: 48, 3: 46, 4: 45, 5: 47,
    6: 55, 7: 68, 8: 85, 9: 95, 10: 88, 11: 78,
    12: 72, 13: 75, 14: 78, 15: 82, 16: 88, 17: 98,
    18: 108, 19: 115, 20: 110, 21: 95, 22: 78, 23: 65,
}

# ── Vizag congestion profile by hour ──────────────────────────────────────
HOURLY_CONGESTION_PROFILE = {
    0: 0.05, 1: 0.04, 2: 0.03, 3: 0.03, 4: 0.04, 5: 0.08,
    6: 0.20, 7: 0.45, 8: 0.70, 9: 0.65, 10: 0.45, 11: 0.40,
    12: 0.50, 13: 0.45, 14: 0.40, 15: 0.45, 16: 0.55, 17: 0.75,
    18: 0.80, 19: 0.72, 20: 0.55, 21: 0.35, 22: 0.20, 23: 0.10,
}


def _aqi_for_ts(ts: datetime) -> float:
    hour = ts.hour
    dow = ts.weekday()
    month = ts.month

    base = HOURLY_AQI_PROFILE[hour]
    # Weekdays 15% higher
    if dow < 5:
        base *= 1.15
    # Monsoon months: June-September lower
    if 6 <= month <= 9:
        base *= 0.80
    # Random noise
    noise = random.gauss(0, 8)
    # Spike: 5% chance
    if random.random() < 0.05:
        base += random.uniform(60, 120)

    return max(5.0, base + noise)


def _traffic_for_ts(ts: datetime) -> tuple[float, float]:
    """Returns (congestion_index, current_speed)."""
    hour = ts.hour
    dow = ts.weekday()
    base_ci = HOURLY_CONGESTION_PROFILE[hour]
    if dow >= 5:
        base_ci *= 0.65
    ci = max(0.0, min(1.0, base_ci + random.gauss(0, 0.04)))
    speed = max(5.0, 60.0 * (1 - ci) + random.gauss(0, 3))
    return ci, speed


async def seed() -> None:
    await init_db()

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=DAYS)
    step = timedelta(minutes=INTERVAL_MINUTES)

    aqi_batch: list[AQIReading] = []
    traffic_batch: list[TrafficReading] = []

    ts = start
    total = 0
    while ts <= now:
        aqi = _aqi_for_ts(ts)
        category, _ = settings.aqi_category(aqi)
        ci, speed = _traffic_for_ts(ts)
        free_flow = 60.0

        aqi_batch.append(AQIReading(
            timestamp=ts,
            source="seed",
            aqi=round(aqi, 1),
            pm25=round(aqi * 0.55 + random.gauss(0, 2), 1),
            pm10=round(aqi * 0.40 + random.gauss(0, 1.5), 1),
            no2=round(12 + aqi * 0.08 + random.gauss(0, 1), 1),
            o3=round(18 + random.gauss(0, 3), 1),
            so2=round(4 + aqi * 0.02, 1),
            co=round(0.8 + aqi * 0.005, 2),
            humidity=round(65 + random.gauss(0, 8), 1),
            temperature=round(28 + random.gauss(0, 3), 1),
            wind_speed=round(max(0, 8 + random.gauss(0, 2)), 1),
            category=category,
            is_anomaly=(aqi > 200),
        ))

        traffic_batch.append(TrafficReading(
            timestamp=ts,
            current_speed=round(speed, 1),
            free_flow_speed=free_flow,
            current_travel_time=int(600 / (speed + 1)),
            free_flow_travel_time=int(600 / free_flow),
            confidence=round(0.85 + random.uniform(-0.05, 0.1), 2),
            road_closure=False,
            congestion_index=round(ci, 3),
            incident_count=random.randint(0, 3) if ci > 0.5 else 0,
        ))

        ts += step
        total += 1

        # Batch write every 1000 records
        if len(aqi_batch) >= 1000:
            async with AsyncSessionLocal() as db:
                db.add_all(aqi_batch)
                db.add_all(traffic_batch)
                await db.commit()
            print(f"  Inserted {total} records up to {ts.strftime('%Y-%m-%d %H:%M')} UTC")
            aqi_batch.clear()
            traffic_batch.clear()

    # Flush remaining
    if aqi_batch:
        async with AsyncSessionLocal() as db:
            db.add_all(aqi_batch)
            db.add_all(traffic_batch)
            await db.commit()

    print(f"\n✅ Seeded {total} AQI + {total} traffic readings ({DAYS} days @ {INTERVAL_MINUTES}min intervals)")
    print(f"   DB: {settings.database_url}")


if __name__ == "__main__":
    print(f"🌱 Seeding historical data ({DAYS} days)...")
    asyncio.run(seed())
