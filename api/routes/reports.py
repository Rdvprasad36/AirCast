from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.database import CitizenReport, get_session

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class ReportCreate(BaseModel):
    city_name: str = Field("Vizag", description="Name of the city")
    latitude: float = Field(..., description="Latitude of the issue")
    longitude: float = Field(..., description="Longitude of the issue")
    issue_type: str = Field(..., description="Type of the issue (e.g., Heavy Traffic)")
    description: Optional[str] = Field(None, description="Optional details")
    severity: int = Field(..., ge=1, le=5, description="Severity from 1 to 5")


class ReportResponse(ReportCreate):
    id: int
    timestamp: datetime


@router.post("/", response_model=ReportResponse)
async def submit_report(
    report_in: ReportCreate,
    session: AsyncSession = Depends(get_session)
):
    """Submit a new citizen report."""
    db_report = CitizenReport(**report_in.model_dump())
    session.add(db_report)
    await session.commit()
    await session.refresh(db_report)
    return db_report.to_dict()


@router.get("/", response_model=List[ReportResponse])
async def get_recent_reports(
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    """Get the most recent citizen reports."""
    result = await session.execute(
        select(CitizenReport).order_by(CitizenReport.timestamp.desc()).limit(limit)
    )
    reports = result.scalars().all()
    return [r.to_dict() for r in reports]
