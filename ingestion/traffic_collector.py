"""
ingestion/traffic_collector.py — Async TomTom traffic collector for Vizag.

Fetches:
  1. Flow data  — current speed vs free-flow speed on key Vizag roads
  2. Incidents  — accidents, road closures, construction

Key TomTom endpoints:
  Flow   : /traffic/services/4/flowSegmentData/relative/{zoom}/json
  Incidents: /traffic/services/5/incidentDetails (bounding box)

Vizag bounding box: 17.60,83.15 → 17.78,83.35
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp

from config import settings
from ingestion.database import TrafficReading, AsyncSessionLocal

logger = logging.getLogger(__name__)

# Key monitoring points across Vizag (lat, lon, label)
VIZAG_MONITORING_POINTS = [
    (17.6868, 83.2185, "Dwarakanagar"),       # City centre
    (17.7231, 83.3012, "Steel Plant Road"),    # Industrial area
    (17.7120, 83.2237, "Jagadamba Junction"),  # Major intersection
    (17.6540, 83.2170, "NAD Junction"),        # Northern corridor
    (17.7420, 83.3310, "Gajuwaka"),            # Outer ring
]

# Vizag bounding box for incident queries
BBOX = "17.60,83.15,17.78,83.35"


async def fetch_flow_data(
    session: aiohttp.ClientSession,
    lat: float,
    lon: float,
) -> dict | None:
    """Fetch TomTom traffic flow for a single geo-point."""
    if not settings.tomtom_api_key:
        logger.warning("No TomTom API key configured — using simulated data.")
        return _simulate_traffic()

    url = (
        "https://api.tomtom.com/traffic/services/4/flowSegmentData"
        f"/relative/10/json?point={lat},{lon}&key={settings.tomtom_api_key}"
    )
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()

        fd = data.get("flowSegmentData", {})
        return {
            "current_speed": fd.get("currentSpeed", 0.0),
            "free_flow_speed": fd.get("freeFlowSpeed", 1.0),
            "current_travel_time": fd.get("currentTravelTime", 0),
            "free_flow_travel_time": fd.get("freeFlowTravelTime", 1),
            "confidence": fd.get("confidence", 1.0),
            "road_closure": fd.get("roadClosure", False),
        }
    except Exception as exc:
        logger.error("TomTom flow fetch failed (%s, %s): %s", lat, lon, exc)
        return None


async def fetch_incidents(session: aiohttp.ClientSession) -> int:
    """Return count of active traffic incidents in Vizag bounding box."""
    if not settings.tomtom_api_key:
        return 0

    url = (
        "https://api.tomtom.com/traffic/services/5/incidentDetails"
        f"?bbox={BBOX}&fields={{incidents{{type,properties{{id}}}}}}"
        f"&language=en-GB&t=1111&timeValidityFilter=present"
        f"&key={settings.tomtom_api_key}"
    )
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
        return len(data.get("incidents", []))
    except Exception as exc:
        logger.error("TomTom incidents fetch failed: %s", exc)
        return 0


def _simulate_traffic() -> dict:
    """
    Return simulated traffic data for demo / no-API-key mode.
    Uses time-of-day heuristics to approximate realistic congestion.
    """
    import random
    from datetime import datetime
    hour = datetime.now().hour
    # Peak hours: 8-10 AM, 5-8 PM
    is_peak = (8 <= hour <= 10) or (17 <= hour <= 20)
    base_speed = 25.0 if is_peak else 45.0
    free_flow = 60.0
    return {
        "current_speed": base_speed + random.uniform(-5, 5),
        "free_flow_speed": free_flow,
        "current_travel_time": int(3600 / (base_speed + 1) * 10),
        "free_flow_travel_time": int(3600 / free_flow * 10),
        "confidence": 0.85,
        "road_closure": False,
    }


def _compute_congestion_index(current: float, free_flow: float) -> float:
    """
    Congestion Index = 1 - (current_speed / free_flow_speed).
    0.0 = free flow, 1.0 = complete standstill.
    """
    if free_flow <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (current / free_flow)))


async def collect_traffic() -> TrafficReading | None:
    """
    Main entry point: aggregate flow data across monitoring points,
    compute a city-level congestion index, persist to DB.
    """
    async with aiohttp.ClientSession() as http:
        flows = []
        for lat, lon, label in VIZAG_MONITORING_POINTS:
            flow = await fetch_flow_data(http, lat, lon)
            if flow:
                flows.append(flow)
                logger.debug("Flow at %s: %s km/h", label, flow["current_speed"])

        incident_count = await fetch_incidents(http)

    if not flows:
        logger.error("No traffic flow data collected.")
        return None

    # Average across all monitoring points
    avg_current = sum(f["current_speed"] for f in flows) / len(flows)
    avg_free = sum(f["free_flow_speed"] for f in flows) / len(flows)
    avg_tt_current = int(sum(f["current_travel_time"] for f in flows) / len(flows))
    avg_tt_free = int(sum(f["free_flow_travel_time"] for f in flows) / len(flows))
    any_closure = any(f.get("road_closure", False) for f in flows)
    avg_confidence = sum(f["confidence"] for f in flows) / len(flows)
    congestion = _compute_congestion_index(avg_current, avg_free)

    reading = TrafficReading(
        timestamp=datetime.now(timezone.utc),
        current_speed=avg_current,
        free_flow_speed=avg_free,
        current_travel_time=avg_tt_current,
        free_flow_travel_time=avg_tt_free,
        confidence=avg_confidence,
        road_closure=any_closure,
        congestion_index=congestion,
        incident_count=incident_count,
    )

    async with AsyncSessionLocal() as db:
        db.add(reading)
        await db.commit()
        await db.refresh(reading)

    logger.info(
        "Traffic collected — congestion=%.2f speed=%.1f km/h incidents=%d",
        reading.congestion_index, reading.current_speed, reading.incident_count,
    )
    return reading
