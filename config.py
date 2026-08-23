"""
config.py — Centralised application configuration.

Loads settings from .env (or environment variables) and exposes
them as a typed Pydantic Settings model used across all modules.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────────
    aqicn_token: str = Field(default="demo", description="AQICN API token")
    owm_api_key: str = Field(default="", description="OpenWeatherMap API key")
    tomtom_api_key: str = Field(default="", description="TomTom API key")

    # ── Database ──────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/vizag.db",
        description="SQLAlchemy async database URL",
    )

    # ── Application ───────────────────────────────────────────────
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    poll_interval_seconds: int = Field(default=300)
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # ── Vizag Location ────────────────────────────────────────────
    vizag_lat: float = Field(default=17.6868)
    vizag_lon: float = Field(default=83.2185)
    vizag_city: str = Field(default="visakhapatnam")

    # ── AQI Alert Thresholds (US EPA) ─────────────────────────────
    alert_good_max: int = Field(default=50)
    alert_moderate_max: int = Field(default=100)
    alert_unhealthy_sensitive_max: int = Field(default=150)
    alert_unhealthy_max: int = Field(default=200)
    alert_very_unhealthy_max: int = Field(default=300)

    # ── Email ─────────────────────────────────────────────────────
    sendgrid_api_key: str = Field(default="")
    alert_from_email: str = Field(default="alerts@vizag-dashboard.app")

    # ── Twilio (SMS/WhatsApp) ─────────────────────────────────────
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_phone_number: str = Field(default="")

    # ── Supabase ──────────────────────────────────────────────────
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def aqi_category(self, aqi: float) -> tuple[str, str]:
        """Return (category_name, hex_color) for a given AQI value."""
        if aqi <= self.alert_good_max:
            return "Good", "#00e400"
        elif aqi <= self.alert_moderate_max:
            return "Moderate", "#ffff00"
        elif aqi <= self.alert_unhealthy_sensitive_max:
            return "Unhealthy for Sensitive Groups", "#ff7e00"
        elif aqi <= self.alert_unhealthy_max:
            return "Unhealthy", "#ff0000"
        elif aqi <= self.alert_very_unhealthy_max:
            return "Very Unhealthy", "#8f3f97"
        else:
            return "Hazardous", "#7e0023"


# Singleton — import this everywhere
settings = Settings()
