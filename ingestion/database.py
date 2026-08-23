"""
ingestion/database.py — Async SQLAlchemy models + DB engine setup.

Schema:
  aqi_readings     — timestamped AQI + pollutant readings
  traffic_readings — timestamped TomTom traffic flow readings
  alert_subscribers — users subscribed to AQI email alerts
  predictions      — stored ML predictions for audit trail
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer,
    String, Text, func, select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & Session Factory
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class AQIReading(Base):
    """One AQI observation from AQICN or OpenWeatherMap."""
    __tablename__ = "aqi_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(50), default="Vizag", index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    source: Mapped[str] = mapped_column(String(20))          # "aqicn" | "owm"
    aqi: Mapped[float] = mapped_column(Float)
    pm25: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm10: Mapped[float | None] = mapped_column(Float, nullable=True)
    no2: Mapped[float | None] = mapped_column(Float, nullable=True)
    o3: Mapped[float | None] = mapped_column(Float, nullable=True)
    so2: Mapped[float | None] = mapped_column(Float, nullable=True)
    co: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(50))        # "Good", "Moderate", …
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TrafficReading(Base):
    """One traffic-flow observation from TomTom."""
    __tablename__ = "traffic_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(50), default="Vizag", index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    current_speed: Mapped[float] = mapped_column(Float)       # km/h
    free_flow_speed: Mapped[float] = mapped_column(Float)     # km/h
    current_travel_time: Mapped[int] = mapped_column(Integer) # seconds
    free_flow_travel_time: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)          # 0–1
    road_closure: Mapped[bool] = mapped_column(Boolean, default=False)
    congestion_index: Mapped[float] = mapped_column(Float)    # 0–1, derived
    incident_count: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Prediction(Base):
    """ML-predicted AQI values stored for audit and display."""
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    forecast_for: Mapped[datetime] = mapped_column(DateTime, index=True)
    predicted_aqi: Mapped[float] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(String(50))       # "xgboost" | "prophet"
    confidence_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_upper: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class AlertSubscriber(Base):
    """Users subscribed to email/SMS AQI alerts."""
    __tablename__ = "alert_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    threshold_aqi: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_alerted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class CitizenReport(Base):
    """Citizen-submitted reports for localized issues."""
    __tablename__ = "citizen_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(50), default="Vizag", index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    issue_type: Mapped[str] = mapped_column(String(50))      # e.g., "Heavy Traffic", "Dust"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[int] = mapped_column(Integer)           # 1 to 5 scale

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables (idempotent). Call once at app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialised — tables ready.")


async def get_session() -> AsyncSession:
    """FastAPI dependency: yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_latest_aqi(session: AsyncSession) -> AQIReading | None:
    result = await session.execute(
        select(AQIReading).order_by(AQIReading.timestamp.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def get_latest_traffic(session: AsyncSession) -> TrafficReading | None:
    result = await session.execute(
        select(TrafficReading).order_by(TrafficReading.timestamp.desc()).limit(1)
    )
    return result.scalar_one_or_none()
