"""
api/routes/history.py — Historical data and export endpoints.

GET  /api/history/aqi          → Paginated AQI readings
GET  /api/history/traffic      → Paginated traffic readings
GET  /api/history/export/csv   → Download all data as CSV
GET  /api/history/export/pdf   → Download summary report as PDF
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.database import AQIReading, TrafficReading, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/aqi")
async def get_aqi_history(
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_session),
):
    """Return recent AQI readings. Default: last 24 hours, up to 100 rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(AQIReading)
            .where(AQIReading.timestamp >= cutoff)
            .order_by(AQIReading.timestamp.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "count": len(rows),
        "hours": hours,
        "readings": [r.to_dict() for r in reversed(rows)],
    }


@router.get("/traffic")
async def get_traffic_history(
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_session),
):
    """Return recent traffic readings."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(TrafficReading)
            .where(TrafficReading.timestamp >= cutoff)
            .order_by(TrafficReading.timestamp.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "count": len(rows),
        "hours": hours,
        "readings": [r.to_dict() for r in reversed(rows)],
    }


@router.get("/export/csv")
async def export_csv(
    hours: int = Query(default=168, ge=1, le=720),  # default: last week
    db: AsyncSession = Depends(get_session),
):
    """Download merged AQI + traffic data as a CSV file."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    aqi_rows = (
        await db.execute(
            select(AQIReading).where(AQIReading.timestamp >= cutoff).order_by(AQIReading.timestamp)
        )
    ).scalars().all()

    traffic_rows = (
        await db.execute(
            select(TrafficReading).where(TrafficReading.timestamp >= cutoff).order_by(TrafficReading.timestamp)
        )
    ).scalars().all()

    aqi_df = pd.DataFrame([r.to_dict() for r in aqi_rows])
    traffic_df = pd.DataFrame([r.to_dict() for r in traffic_rows])

    if aqi_df.empty:
        raise HTTPException(status_code=404, detail="No data found for the specified period.")

    # Merge on nearest timestamp
    if not traffic_df.empty:
        aqi_df["timestamp"] = pd.to_datetime(aqi_df["timestamp"])
        traffic_df["timestamp"] = pd.to_datetime(traffic_df["timestamp"])
        merged = pd.merge_asof(
            aqi_df.sort_values("timestamp"),
            traffic_df[["timestamp", "congestion_index", "current_speed", "incident_count"]].sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("15min"),
            suffixes=("_aqi", "_traffic"),
        )
    else:
        merged = aqi_df

    buf = io.StringIO()
    merged.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"vizag_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/pdf")
async def export_pdf(
    hours: int = Query(default=168, ge=1, le=720),
    db: AsyncSession = Depends(get_session),
):
    """Generate and download a summary PDF report."""
    try:
        from fpdf import FPDF
    except ImportError:
        raise HTTPException(status_code=501, detail="fpdf2 not installed.")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    aqi_rows = (
        await db.execute(
            select(AQIReading).where(AQIReading.timestamp >= cutoff).order_by(AQIReading.timestamp)
        )
    ).scalars().all()

    if not aqi_rows:
        raise HTTPException(status_code=404, detail="No data available for report.")

    df = pd.DataFrame([r.to_dict() for r in aqi_rows])

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "Vizag Traffic & Pollution Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M IST')} | Period: {hours}h", ln=True, align="C")
    pdf.ln(6)

    # Summary table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "AQI Summary", ln=True)
    pdf.set_font("Helvetica", "", 10)

    stats = [
        ("Mean AQI", f"{df['aqi'].mean():.1f}"),
        ("Max AQI", f"{df['aqi'].max():.1f}"),
        ("Min AQI", f"{df['aqi'].min():.1f}"),
        ("Anomalies Detected", str(df.get("is_anomaly", pd.Series([False])).sum())),
        ("Total Readings", str(len(df))),
        ("Data Sources", ", ".join(df["source"].unique())),
    ]
    for label, value in stats:
        pdf.cell(70, 8, label + ":", border=0)
        pdf.cell(0, 8, value, ln=True)

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "AQI Category Breakdown", ln=True)
    pdf.set_font("Helvetica", "", 10)
    for cat, count in df["category"].value_counts().items():
        pdf.cell(70, 8, str(cat) + ":")
        pdf.cell(0, 8, f"{count} readings ({count/len(df)*100:.1f}%)", ln=True)

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)

    filename = f"vizag_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
