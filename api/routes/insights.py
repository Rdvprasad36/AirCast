from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ingestion.database import get_session
import random

router = APIRouter(prefix="/api/insights", tags=["Insights"])

@router.get("/root-cause")
async def get_root_cause(city: str = "Visakhapatnam", session: AsyncSession = Depends(get_session)):
    # Simulate LLM Analysis since we don't have an API key loaded
    explanations = [
        f"AQI in {city} spiked due to a combination of 15% higher traffic congestion and stagnant wind speeds.",
        f"High PM2.5 levels detected near industrial zones in {city} likely caused by recent factory emissions combined with low humidity.",
        f"Traffic congestion is contributing to localized poor air quality in the moderate zone across {city}."
    ]
    return {
        "status": "success",
        "city": city,
        "insight": random.choice(explanations),
        "model": "gemini-simulated"
    }
