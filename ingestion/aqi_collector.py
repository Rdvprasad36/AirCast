"""
ingestion/aqi_collector.py — Async AQI data collector.

Primary source : AQICN (real-time station data for Vizag)
Fallback source: OpenWeatherMap Air Pollution API (satellite-based)

Both are normalised to the same AQIReading schema before storage.
OWM uses a 1-5 scale — we map it to an approximate US-EPA AQI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp

from config import settings
from ingestion.database import AQIReading, AsyncSessionLocal

logger = logging.getLogger(__name__)

# OWM AQI index (1–5) → approximate US-EPA AQI midpoint mapping
OWM_AQI_MAP = {1: 25, 2: 75, 3: 125, 4: 175, 5: 250}


# ---------------------------------------------------------------------------
# AQICN Collector
# ---------------------------------------------------------------------------

async def fetch_aqicn(session: aiohttp.ClientSession) -> dict | None:
    """
    Fetch real-time AQI from AQICN for Visakhapatnam.
    Endpoint: https://api.waqi.info/feed/visakhapatnam/?token=TOKEN
    """
    url = (
        f"https://api.waqi.info/feed/{settings.vizag_city}/"
        f"?token={settings.aqicn_token}"
    )
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()

        if data.get("status") != "ok":
            logger.warning("AQICN returned non-ok status: %s", data)
            return None

        d = data["data"]
        iaqi = d.get("iaqi", {})

        return {
            "source": "aqicn",
            "aqi": float(d["aqi"]),
            "pm25": iaqi.get("pm25", {}).get("v"),
            "pm10": iaqi.get("pm10", {}).get("v"),
            "no2": iaqi.get("no2", {}).get("v"),
            "o3": iaqi.get("o3", {}).get("v"),
            "so2": iaqi.get("so2", {}).get("v"),
            "co": iaqi.get("co", {}).get("v"),
            "humidity": iaqi.get("h", {}).get("v"),
            "temperature": iaqi.get("t", {}).get("v"),
            "wind_speed": iaqi.get("w", {}).get("v"),
        }

    except Exception as exc:
        logger.error("AQICN fetch failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# OpenWeatherMap Fallback
# ---------------------------------------------------------------------------

async def fetch_owm_aqi(session: aiohttp.ClientSession) -> dict | None:
    """
    Fetch AQI from OpenWeatherMap Air Pollution API.
    Returns None if no OWM key is configured.
    OWM AQI scale: 1=Good … 5=Very Poor (converted to ~US-EPA scale).
    """
    if not settings.owm_api_key:
        return None

    url = (
        "http://api.openweathermap.org/data/2.5/air_pollution"
        f"?lat={settings.vizag_lat}&lon={settings.vizag_lon}"
        f"&appid={settings.owm_api_key}"
    )
    weather_url = (
        "http://api.openweathermap.org/data/2.5/weather"
        f"?lat={settings.vizag_lat}&lon={settings.vizag_lon}"
        f"&appid={settings.owm_api_key}&units=metric"
    )

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            ap_data = await resp.json()
        async with session.get(weather_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            wx_data = await resp.json()

        comp = ap_data["list"][0]["components"]
        owm_aqi = ap_data["list"][0]["main"]["aqi"]
        approx_us_aqi = float(OWM_AQI_MAP.get(owm_aqi, 100))

        return {
            "source": "owm",
            "aqi": approx_us_aqi,
            "pm25": comp.get("pm2_5"),
            "pm10": comp.get("pm10"),
            "no2": comp.get("no2"),
            "o3": comp.get("o3"),
            "so2": comp.get("so2"),
            "co": comp.get("co"),
            "humidity": wx_data.get("main", {}).get("humidity"),
            "temperature": wx_data.get("main", {}).get("temp"),
            "wind_speed": wx_data.get("wind", {}).get("speed"),
        }

    except Exception as exc:
        logger.error("OWM fetch failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Unified Collector — tries AQICN first, falls back to OWM
# ---------------------------------------------------------------------------

async def collect_aqi() -> AQIReading | None:
    """
    Main entry point: fetch AQI data, persist to DB, return the ORM object.

    Priority:
      1. AQICN (live station)
      2. OpenWeatherMap (satellite model)
    """
    async with aiohttp.ClientSession() as http:
        raw = await fetch_aqicn(http)
        if raw is None:
            logger.info("AQICN unavailable, falling back to OWM.")
            raw = await fetch_owm_aqi(http)

    if raw is None:
        logger.error("Both AQI sources failed. Skipping this cycle.")
        return None

    category, _ = settings.aqi_category(raw["aqi"])
    reading = AQIReading(
        timestamp=datetime.now(timezone.utc),
        category=category,
        **raw,
    )

    async with AsyncSessionLocal() as db:
        db.add(reading)
        await db.commit()
        await db.refresh(reading)

    logger.info(
        "AQI collected — source=%s aqi=%.1f category=%s",
        reading.source, reading.aqi, reading.category,
    )
    return reading
