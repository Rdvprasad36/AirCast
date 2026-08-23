from fastapi import APIRouter
from ingestion.events_collector import get_current_events, get_weather_context, get_context_summary

router = APIRouter(prefix="/api/context", tags=["Context"])

@router.get("/events")
async def get_events(city: str = "Visakhapatnam"):
    return {"events": get_current_events(city)}

@router.get("/weather")
async def get_weather(city: str = "Visakhapatnam"):
    return get_weather_context(city)

@router.get("/summary")
async def get_summary(city: str = "Visakhapatnam"):
    return get_context_summary(city)
