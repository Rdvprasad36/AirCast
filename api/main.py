"""
api/main.py — FastAPI application entry point.

Routes:
  GET  /                        → Health check
  GET  /api/live/aqi            → Latest AQI reading
  GET  /api/live/traffic        → Latest traffic reading
  GET  /api/predict/next-hour   → XGBoost/Prophet next-hour AQI
  GET  /api/predict/next/{n}    → Multi-hour forecast
  GET  /api/history/aqi         → Paginated AQI history
  GET  /api/history/traffic     → Paginated traffic history
  POST /api/alerts/subscribe    → Subscribe to email AQI alerts
  GET  /api/history/export      → Download CSV / PDF report
  GET  /api/live/stats          → Correlation stats (traffic vs AQI)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from ingestion.database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, warm up models, start data scheduler."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger.info("🚀 Vizag Dashboard API starting...")

    # Ensure data directory + DB tables exist
    import os
    os.makedirs("data", exist_ok=True)
    await init_db()

    # Try to warm up ML models
    try:
        from ml.predictor import XGBOOST_PATH, PROPHET_PATH
        if XGBOOST_PATH.exists() or PROPHET_PATH.exists():
            logger.info("ML models found — ready for predictions.")
        else:
            logger.warning(
                "No ML models found. Run `python scripts/train_model.py` "
                "or wait for the first scheduled retrain (6 h)."
            )
    except Exception as exc:
        logger.warning("Model warm-up failed: %s", exc)

    # Start background data collection
    from ingestion.scheduler import start_scheduler
    scheduler_task = asyncio.create_task(start_scheduler())
    logger.info("✅ Background data scheduler started.")

    yield  # Application running

    # Teardown
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    logger.info("👋 Vizag Dashboard API shutting down.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Vizag Traffic & Pollution Dashboard API",
    description=(
        "Real-time traffic and air quality analytics for Visakhapatnam. "
        "Streams live AQI + traffic data, detects anomalies, and predicts "
        "next-hour AQI using XGBoost and Prophet models."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow Streamlit dashboard and any front-end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Import and register routers
# ---------------------------------------------------------------------------

from api.routes.live import router as live_router
from api.routes.predict import router as predict_router
from api.routes.history import router as history_router
from api.routes.alerts import router as alerts_router
from api.routes.reports import router as reports_router
from api.routes.insights import router as insights_router
from api.routes.rerouting import router as rerouting_router
from api.routes.context import router as context_router

app.include_router(live_router, prefix="/api/live", tags=["Live Data"])
app.include_router(predict_router, prefix="/api/predict", tags=["Predictions"])
app.include_router(history_router, prefix="/api/history", tags=["History"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(reports_router)
app.include_router(insights_router)
app.include_router(rerouting_router)
app.include_router(context_router)



@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "service": "Vizag Traffic & Pollution Dashboard",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
