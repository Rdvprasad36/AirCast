"""
api/routes/alerts.py — Alert subscription and dispatch endpoints.

POST /api/alerts/subscribe    → Subscribe email to AQI threshold alerts
DELETE /api/alerts/unsubscribe → Unsubscribe an email
GET  /api/alerts/subscribers  → List all active subscribers (admin)
POST /api/alerts/test-sms     → Send a test SMS alert

Internal:
  dispatch_aqi_alerts(aqi)  → Called by scheduler after each reading
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from ingestion.database import AlertSubscriber, AsyncSessionLocal, get_session
from ingestion.notifications import send_sms_alert

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class SubscribeRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    threshold_aqi: int = Field(default=100, ge=0, le=500,
                                description="Alert when AQI exceeds this value")


class SubscribeResponse(BaseModel):
    message: str
    email: str
    threshold_aqi: int


class TestSMSRequest(BaseModel):
    phone: str = Field(..., description="Recipient phone number with country code (e.g. +919876543210)")
    message: str | None = Field(default=None, description="Optional custom test message")


class TestSMSResponse(BaseModel):
    success: bool
    message: str
    phone: str


# ---------------------------------------------------------------------------
# Email Dispatch (SendGrid)
# ---------------------------------------------------------------------------

async def _send_email(to_email: str, name: str, aqi: float, category: str) -> bool:
    """Send AQI alert email via SendGrid. Returns True on success."""
    if not settings.sendgrid_api_key:
        logger.info("No SendGrid key — would send alert to %s (AQI=%.1f)", to_email, aqi)
        return True   # Silently succeed in dev mode

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        msg = Mail(
            from_email=settings.alert_from_email,
            to_emails=to_email,
            subject=f"⚠️ Vizag AQI Alert: {category} (AQI {aqi:.0f})",
            html_content=f"""
            <div style="font-family:sans-serif;max-width:500px">
              <h2 style="color:#e53e3e">🌫️ Air Quality Alert — Visakhapatnam</h2>
              <p>Hi <strong>{name}</strong>,</p>
              <p>The AQI in Vizag has reached <strong>{aqi:.0f}</strong>
                 (<span style="color:#e53e3e">{category}</span>).</p>
              <table style="border-collapse:collapse;width:100%">
                <tr><td style="padding:4px 8px;font-weight:bold">AQI Level</td>
                    <td style="padding:4px 8px">{aqi:.0f}</td></tr>
                <tr><td style="padding:4px 8px;font-weight:bold">Category</td>
                    <td style="padding:4px 8px">{category}</td></tr>
                <tr><td style="padding:4px 8px;font-weight:bold">Time</td>
                    <td style="padding:4px 8px">{datetime.now().strftime('%Y-%m-%d %H:%M IST')}</td></tr>
              </table>
              <p style="margin-top:16px">
                <a href="https://aqicn.org/city/india/visakhapatnam/">View on AQICN →</a>
              </p>
              <p style="color:#666;font-size:12px">
                You are receiving this because you subscribed at Vizag Dashboard.
                <a href="#">Unsubscribe</a>
              </p>
            </div>
            """,
        )
        sg.send(msg)
        logger.info("Alert email sent to %s", to_email)
        return True

    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


# ---------------------------------------------------------------------------
# Dispatch Logic (called by scheduler)
# ---------------------------------------------------------------------------

_ALERT_COOLDOWN_HOURS = 3  # Don't spam: max 1 alert per subscriber per 3 h


async def dispatch_aqi_alerts(current_aqi: float) -> None:
    """
    Check all active subscribers. Send email if:
      - Current AQI exceeds their threshold
      - They haven't been alerted in the last 3 hours
    """
    async with AsyncSessionLocal() as db:
        subscribers = (
            await db.execute(
                select(AlertSubscriber).where(AlertSubscriber.is_active == True)
            )
        ).scalars().all()

    if not subscribers:
        return

    category, _ = settings.aqi_category(current_aqi)
    now = datetime.now(timezone.utc)
    cooldown = timedelta(hours=_ALERT_COOLDOWN_HOURS)

    for sub in subscribers:
        if current_aqi < sub.threshold_aqi:
            continue

        # Cooldown check
        if sub.last_alerted_at and (now - sub.last_alerted_at.replace(tzinfo=timezone.utc)) < cooldown:
            logger.debug("Skipping alert for %s (cooldown active)", sub.email)
            continue

        sent = await _send_email(sub.email, sub.name, current_aqi, category)
        if sent:
            async with AsyncSessionLocal() as db:
                sub_refreshed = await db.get(AlertSubscriber, sub.id)
                if sub_refreshed:
                    sub_refreshed.last_alerted_at = now
                    await db.commit()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    req: SubscribeRequest,
    db: AsyncSession = Depends(get_session),
):
    """Subscribe an email address to AQI threshold alerts."""
    existing = (
        await db.execute(
            select(AlertSubscriber).where(AlertSubscriber.email == req.email)
        )
    ).scalar_one_or_none()

    if existing:
        existing.threshold_aqi = req.threshold_aqi
        existing.name = req.name
        existing.is_active = True
        await db.commit()
        return SubscribeResponse(
            message="Subscription updated.",
            email=req.email,
            threshold_aqi=req.threshold_aqi,
        )

    subscriber = AlertSubscriber(
        email=req.email,
        name=req.name,
        threshold_aqi=req.threshold_aqi,
    )
    db.add(subscriber)
    await db.commit()
    return SubscribeResponse(
        message="Subscribed successfully! You'll receive alerts when AQI exceeds your threshold.",
        email=req.email,
        threshold_aqi=req.threshold_aqi,
    )


@router.delete("/unsubscribe")
async def unsubscribe(
    email: str,
    db: AsyncSession = Depends(get_session),
):
    """Unsubscribe an email from AQI alerts."""
    subscriber = (
        await db.execute(
            select(AlertSubscriber).where(AlertSubscriber.email == email)
        )
    ).scalar_one_or_none()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Email not found.")

    subscriber.is_active = False
    await db.commit()
    return {"message": f"{email} unsubscribed successfully."}


@router.get("/subscribers")
async def list_subscribers(db: AsyncSession = Depends(get_session)):
    """List all active subscribers (admin view — add auth in production!)."""
    rows = (
        await db.execute(
            select(AlertSubscriber).where(AlertSubscriber.is_active == True)
        )
    ).scalars().all()
    return {"count": len(rows), "subscribers": [r.to_dict() for r in rows]}


@router.post("/test-sms", response_model=TestSMSResponse)
async def test_sms(req: TestSMSRequest):
    """Send a test SMS alert to verify Twilio configuration."""
    msg = req.message or "⚠️ [Test Alert] Vizag AQI has reached 155 (Unhealthy). Please take precautions."
    success = send_sms_alert(phone=req.phone, message=msg)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send SMS to {req.phone}. Check Twilio credentials and server logs.",
        )
    return TestSMSResponse(
        success=True,
        message=f"Test SMS dispatched to {req.phone}.",
        phone=req.phone,
    )
