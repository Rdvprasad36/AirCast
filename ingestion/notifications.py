"""
ingestion/notifications.py — Multi-Channel Alerts (Email, SMS & WhatsApp via Twilio).

Provides alert dispatch functions across multiple notification channels:
- Email (via SendGrid)
- SMS (via Twilio)
- WhatsApp (via Twilio WhatsApp API)

All functions gracefully fall back to simulated logging when credentials
are not configured.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# Graceful Twilio import
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    Client = None  # type: ignore


def _is_configured(val: str | None) -> bool:
    """Helper to check if an API key / value is present and not a dummy placeholder."""
    if not val:
        return False
    v = val.strip().lower()
    return not (v == "" or v.startswith("your_") or "placeholder" in v or "dummy" in v)


def _get_twilio_client() -> tuple[Any | None, str]:
    """
    Initialize and return a Twilio Client instance and account SID if configured.
    Checks config.settings first, then os.environ.
    """
    if not TWILIO_AVAILABLE:
        return None, ""

    account_sid = (
        getattr(settings, "twilio_account_sid", "")
        or os.getenv("TWILIO_ACCOUNT_SID", "")
    ).strip()
    auth_token = (
        getattr(settings, "twilio_auth_token", "")
        or os.getenv("TWILIO_AUTH_TOKEN", "")
    ).strip()

    if not _is_configured(account_sid) or not _is_configured(auth_token):
        return None, ""

    try:
        client = Client(account_sid, auth_token)
        return client, account_sid
    except Exception as exc:
        logger.error("Failed to initialize Twilio Client: %s", exc)
        return None, ""


def send_sms_alert(phone: str, message: str) -> bool:
    """
    Send an SMS alert via Twilio.
    Falls back to simulated logging if Twilio credentials are not set.
    """
    client, _ = _get_twilio_client()
    from_number = (
        getattr(settings, "twilio_phone_number", "")
        or os.getenv("TWILIO_PHONE_NUMBER", "")
    ).strip()

    if not client or not _is_configured(from_number):
        logger.info(
            "[SIMULATED SMS] Recipient: %s | Message: %s",
            phone,
            message,
        )
        return True

    try:
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=phone,
        )
        logger.info("SMS alert sent successfully to %s (SID: %s)", phone, msg.sid)
        return True
    except Exception as exc:
        logger.error("Failed to send SMS alert to %s: %s", phone, exc)
        return False


def send_whatsapp_alert(phone: str, message: str) -> bool:
    """
    Send a WhatsApp alert via Twilio WhatsApp API.
    Falls back to simulated logging if Twilio credentials are not set.
    """
    client, _ = _get_twilio_client()
    from_number = (
        getattr(settings, "twilio_phone_number", "")
        or os.getenv("TWILIO_PHONE_NUMBER", "")
    ).strip()

    if not client or not _is_configured(from_number):
        logger.info(
            "[SIMULATED WHATSAPP] Recipient: %s | Message: %s",
            phone,
            message,
        )
        return True

    try:
        from_wa = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        to_wa = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"

        msg = client.messages.create(
            body=message,
            from_=from_wa,
            to=to_wa,
        )
        logger.info("WhatsApp alert sent successfully to %s (SID: %s)", phone, msg.sid)
        return True
    except Exception as exc:
        logger.error("Failed to send WhatsApp alert to %s: %s", phone, exc)
        return False


def send_email_alert(
    to_email: str,
    name: str,
    aqi_value: float,
    category: str,
    city: str = "Visakhapatnam",
) -> bool:
    """
    Send an AQI alert email via SendGrid.
    Falls back to simulated logging if SendGrid is unconfigured.
    """
    api_key = (
        getattr(settings, "sendgrid_api_key", "")
        or os.getenv("SENDGRID_API_KEY", "")
    ).strip()

    if not _is_configured(api_key):
        logger.info(
            "[SIMULATED EMAIL] Recipient: %s (%s) | AQI: %.1f (%s) in %s",
            to_email,
            name,
            aqi_value,
            category,
            city,
        )
        return True

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M IST")
        html_body = f"""
        <div style="font-family:sans-serif;max-width:500px">
          <h2 style="color:#e53e3e">🌫️ Air Quality Alert — {city}</h2>
          <p>Hi <strong>{name}</strong>,</p>
          <p>The AQI in {city} has reached <strong>{aqi_value:.0f}</strong>
             (<span style="color:#e53e3e">{category}</span>).</p>
          <table style="border-collapse:collapse;width:100%">
            <tr><td style="padding:4px 8px;font-weight:bold">AQI Level</td>
                <td style="padding:4px 8px">{aqi_value:.0f}</td></tr>
            <tr><td style="padding:4px 8px;font-weight:bold">Category</td>
                <td style="padding:4px 8px">{category}</td></tr>
            <tr><td style="padding:4px 8px;font-weight:bold">Time</td>
                <td style="padding:4px 8px">{timestamp_str}</td></tr>
          </table>
          <p style="margin-top:16px">
            <a href="https://aqicn.org/city/india/visakhapatnam/">View on AQICN →</a>
          </p>
          <p style="color:#666;font-size:12px">
            You are receiving this because you subscribed at Vizag Dashboard.
          </p>
        </div>
        """
        msg = Mail(
            from_email=settings.alert_from_email,
            to_emails=to_email,
            subject=f"⚠️ {city} AQI Alert: {category} (AQI {aqi_value:.0f})",
            html_content=html_body,
        )
        sg.send(msg)
        logger.info("Alert email sent successfully to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send alert email to %s: %s", to_email, exc)
        return False


def send_multi_channel_alert(
    subscriber_data: dict | Any,
    aqi_value: float,
    city: str = "Visakhapatnam",
) -> dict[str, bool]:
    """
    Send multi-channel notifications (Email, SMS, WhatsApp) for an AQI alert.
    
    Args:
        subscriber_data: Dict or ORM object containing subscriber details (email, phone/phone_number, name).
        aqi_value: The AQI reading that triggered the alert.
        city: City name (default: Visakhapatnam).
        
    Returns:
        Dictionary indicating status for each channel: {"email": bool, "sms": bool, "whatsapp": bool}
    """
    if isinstance(subscriber_data, dict):
        email = subscriber_data.get("email")
        phone = subscriber_data.get("phone") or subscriber_data.get("phone_number")
        name = subscriber_data.get("name", "Subscriber")
    else:
        email = getattr(subscriber_data, "email", None)
        phone = getattr(subscriber_data, "phone", None) or getattr(subscriber_data, "phone_number", None)
        name = getattr(subscriber_data, "name", "Subscriber")

    category, _ = settings.aqi_category(aqi_value)
    results: dict[str, bool] = {
        "email": False,
        "sms": False,
        "whatsapp": False,
    }

    # 1. Email notification
    if email:
        results["email"] = send_email_alert(
            to_email=email,
            name=name,
            aqi_value=aqi_value,
            category=category,
            city=city,
        )

    # 2. SMS notification
    if phone:
        sms_body = (
            f"⚠️ {city} Air Quality Alert: AQI is {aqi_value:.0f} ({category}). "
            f"Please take necessary precautions."
        )
        results["sms"] = send_sms_alert(phone=phone, message=sms_body)

    # 3. WhatsApp notification
    if phone:
        whatsapp_body = (
            f"🚨 *Air Quality Alert — {city}*\n\n"
            f"Hi *{name}*,\n"
            f"The AQI in {city} has reached *{aqi_value:.0f}* ({category}).\n\n"
            f"Health Advisory: Limit prolonged outdoor exertion and consider wearing a mask."
        )
        results["whatsapp"] = send_whatsapp_alert(phone=phone, message=whatsapp_body)

    return results
