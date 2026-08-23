from fastapi import APIRouter
from datetime import datetime, timedelta
import random

router = APIRouter(prefix="/api/rerouting", tags=["Traffic Re-routing"])

# Major routes in AP cities
CITY_ROUTES = {
    "Visakhapatnam": [
        {"name": "Beach Road → Steel Plant", "distance_km": 12, "normal_time_min": 25},
        {"name": "Jagadamba → Gajuwaka", "distance_km": 8, "normal_time_min": 20},
        {"name": "NAD Junction → RK Beach", "distance_km": 15, "normal_time_min": 35},
        {"name": "Maddilapalem → Simhachalam", "distance_km": 10, "normal_time_min": 22},
    ],
    "Vijayawada": [
        {"name": "Benz Circle → Kanaka Durga Temple", "distance_km": 5, "normal_time_min": 15},
        {"name": "Governorpet → Eluru Road", "distance_km": 7, "normal_time_min": 18},
        {"name": "Auto Nagar → Gannavaram", "distance_km": 14, "normal_time_min": 30},
    ],
}

@router.get("/suggestions")
async def get_rerouting_suggestions(city: str = "Visakhapatnam"):
    routes = CITY_ROUTES.get(city, CITY_ROUTES.get("Visakhapatnam", []))
    random.seed(hash(city + datetime.now().strftime('%Y-%m-%d-%H')))
    
    suggestions = []
    for route in routes:
        congestion = round(random.uniform(0.1, 0.9), 2)
        current_time_min = int(route["normal_time_min"] * (1 + congestion))
        aqi_impact = round(random.uniform(5, 30), 1)
        
        alt_congestion = max(0.05, congestion - random.uniform(0.1, 0.3))
        alt_time_min = int(route["normal_time_min"] * (1 + alt_congestion))
        
        suggestions.append({
            "route": route["name"],
            "distance_km": route["distance_km"],
            "current_congestion": congestion,
            "current_travel_time_min": current_time_min,
            "predicted_aqi_contribution": aqi_impact,
            "alternative": {
                "suggested_time": (datetime.now() + timedelta(hours=random.randint(1, 3))).strftime("%H:%M"),
                "estimated_congestion": alt_congestion,
                "estimated_travel_time_min": alt_time_min,
                "aqi_reduction_percent": round((1 - alt_congestion/max(congestion, 0.01)) * 100, 1),
            },
            "recommendation": "Delay travel" if congestion > 0.6 else "Take alternate route" if congestion > 0.3 else "Clear to travel",
        })
    
    return {"city": city, "suggestions": suggestions, "generated_at": datetime.now().isoformat()}
