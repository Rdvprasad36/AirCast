"""
ingestion/events_collector.py — Local events and advanced weather data.

Provides context for why traffic or pollution spikes might occur.
"""
import random
from datetime import datetime, timedelta

# Andhra Pradesh city coordinates
AP_CITIES = {
    "Visakhapatnam": {"lat": 17.6868, "lon": 83.2185},
    "Vijayawada": {"lat": 16.5062, "lon": 80.6480},
    "Guntur": {"lat": 16.3067, "lon": 80.4365},
    "Tirupati": {"lat": 13.6288, "lon": 79.4192},
    "Nellore": {"lat": 14.4426, "lon": 79.9865},
    "Kurnool": {"lat": 15.8281, "lon": 78.0373},
}

# Simulated local events database
LOCAL_EVENTS = [
    {"name": "Dasara Festival", "type": "festival", "impact": "high", "traffic_multiplier": 1.8},
    {"name": "IPL Cricket Match", "type": "sports", "impact": "high", "traffic_multiplier": 2.0},
    {"name": "Weekly Market Day", "type": "market", "impact": "medium", "traffic_multiplier": 1.4},
    {"name": "School Reopening", "type": "education", "impact": "medium", "traffic_multiplier": 1.3},
    {"name": "Industrial Zone Maintenance", "type": "industrial", "impact": "low", "traffic_multiplier": 1.1},
    {"name": "Beach Festival", "type": "cultural", "impact": "medium", "traffic_multiplier": 1.5},
    {"name": "Political Rally", "type": "political", "impact": "high", "traffic_multiplier": 1.7},
    {"name": "Temple Procession", "type": "religious", "impact": "medium", "traffic_multiplier": 1.6},
]


def get_current_events(city: str) -> list[dict]:
    """Get simulated current/upcoming events for a city."""
    random.seed(hash(city + datetime.now().strftime('%Y-%m-%d')))
    num_events = random.randint(0, 3)
    events = []
    for _ in range(num_events):
        event = random.choice(LOCAL_EVENTS).copy()
        event["city"] = city
        event["date"] = (datetime.now() + timedelta(hours=random.randint(-6, 48))).isoformat()
        events.append(event)
    return events


def get_weather_context(city: str) -> dict:
    """Get simulated advanced weather data including wind vectors."""
    coords = AP_CITIES.get(city, AP_CITIES["Visakhapatnam"])
    random.seed(hash(city + datetime.now().strftime('%Y-%m-%d-%H')))
    
    wind_direction = random.choice(["N", "NE", "E", "SE", "S", "SW", "W", "NW"])
    wind_speed = round(random.uniform(2, 25), 1)
    humidity = round(random.uniform(40, 95), 1)
    temperature = round(random.uniform(24, 42), 1)
    pressure = round(random.uniform(1005, 1020), 1)
    visibility = round(random.uniform(2, 10), 1)
    
    # Determine if wind is blowing from industrial zone
    industrial_wind = wind_direction in ["SW", "W", "NW"]
    
    return {
        "city": city,
        "coordinates": coords,
        "wind": {
            "direction": wind_direction,
            "speed_kmh": wind_speed,
            "from_industrial_zone": industrial_wind,
        },
        "humidity_percent": humidity,
        "temperature_celsius": temperature,
        "pressure_hpa": pressure,
        "visibility_km": visibility,
        "stagnant_air": wind_speed < 5,
        "pollution_dispersal": "poor" if wind_speed < 5 else "moderate" if wind_speed < 15 else "good",
    }


def get_context_summary(city: str) -> dict:
    """Get combined events + weather context for a city."""
    events = get_current_events(city)
    weather = get_weather_context(city)
    
    warnings = []
    if weather["stagnant_air"]:
        warnings.append("Stagnant air conditions — pollutants may accumulate")
    if weather["wind"]["from_industrial_zone"]:
        warnings.append(f"Wind blowing from industrial zone ({weather['wind']['direction']})")
    for event in events:
        if event["impact"] == "high":
            warnings.append(f"High-impact event: {event['name']} — expect {(event['traffic_multiplier']-1)*100:.0f}% more traffic")
    
    return {
        "city": city,
        "events": events,
        "weather": weather,
        "warnings": warnings,
        "risk_level": "high" if len(warnings) >= 2 else "medium" if warnings else "low",
    }
