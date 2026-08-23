"""
ingestion/scheduler.py — asyncio-based background data polling scheduler.

Runs two periodic tasks:
  • collect_aqi()     — every POLL_INTERVAL_SECONDS (default 5 min)
  • collect_traffic() — every POLL_INTERVAL_SECONDS

Also triggers:
  • anomaly detection after each AQI reading
  • alert dispatch when AQI exceeds subscriber thresholds
  • ML model retrain every 6 hours (if enough data exists)

Usage:
  python -m ingestion.scheduler          (standalone)
  asyncio.create_task(start_scheduler()) (embedded in FastAPI lifespan)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from config import settings
from ingestion.aqi_collector import collect_aqi
from ingestion.traffic_collector import collect_traffic

logger = logging.getLogger(__name__)

_RETRAIN_INTERVAL_HOURS = 6
_retrain_counter = 0


async def _run_aqi_cycle() -> None:
    """Single AQI collection + anomaly detection cycle."""
    try:
        reading = await collect_aqi()
        if reading is None:
            return

        # Lazy import to avoid circular deps at module load
        from processing.anomaly_detection import flag_anomaly_if_needed
        from api.routes.alerts import dispatch_aqi_alerts

        await flag_anomaly_if_needed(reading)
        await dispatch_aqi_alerts(reading.aqi)

    except Exception as exc:
        logger.exception("AQI cycle error: %s", exc)


async def _run_traffic_cycle() -> None:
    """Single traffic collection cycle."""
    try:
        await collect_traffic()
    except Exception as exc:
        logger.exception("Traffic cycle error: %s", exc)


async def _run_retrain_cycle() -> None:
    """Retrain ML models with latest data (runs every 6 h)."""
    global _retrain_counter
    _retrain_counter += 1

    from ml.predictor import retrain_models
    try:
        logger.info("Scheduled retrain #%d starting...", _retrain_counter)
        await asyncio.to_thread(retrain_models)
        logger.info("Scheduled retrain #%d complete.", _retrain_counter)
    except Exception as exc:
        logger.exception("Retrain cycle error: %s", exc)


async def _periodic(coro_fn, interval_seconds: int, label: str) -> None:
    """Run *coro_fn* immediately, then every *interval_seconds*."""
    logger.info("Starting periodic task '%s' (interval=%ds)", label, interval_seconds)
    while True:
        start = datetime.utcnow()
        await coro_fn()
        elapsed = (datetime.utcnow() - start).total_seconds()
        sleep_time = max(0, interval_seconds - elapsed)
        logger.debug("Task '%s' done in %.1fs, sleeping %.1fs", label, elapsed, sleep_time)
        await asyncio.sleep(sleep_time)


async def start_scheduler() -> None:
    """
    Launch all background tasks.
    Call this from FastAPI lifespan or run as __main__.
    """
    retrain_interval = _RETRAIN_INTERVAL_HOURS * 3600

    await asyncio.gather(
        _periodic(_run_aqi_cycle, settings.poll_interval_seconds, "aqi"),
        _periodic(_run_traffic_cycle, settings.poll_interval_seconds, "traffic"),
        _periodic(_run_retrain_cycle, retrain_interval, "retrain"),
    )


if __name__ == "__main__":
    import os
    import sys

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger.info("Starting standalone scheduler for Vizag Dashboard...")
    asyncio.run(start_scheduler())
