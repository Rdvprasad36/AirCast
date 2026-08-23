# Vizag Traffic & Pollution Dashboard

> **Hackathon Category**: Smart City / Environment  
> **Stack**: Python · FastAPI · Streamlit · XGBoost · Prophet · SQLite/Supabase

Real-time analytics platform that streams live traffic and air quality data for **Visakhapatnam, India**, correlates them, and predicts next-hour AQI using machine learning.

---

## 📸 Features

| Feature | Description |
|---------|-------------|
| 🗺️ **Live Traffic Heatmap** | Folium map with TomTom traffic overlay across 5 Vizag monitoring points |
| 📈 **Real-Time AQI Trend** | Plotly chart with PM2.5 overlay, anomaly markers, and AQI zone bands |
| 🔮 **ML Prediction** | XGBoost (primary) + Prophet (baseline) — next-hour and 6-hour AQI forecast with 90% CI |
| 🚨 **Anomaly Detection** | IsolationForest flags unusual AQI spikes in real time |
| 🔔 **Email Alerts** | Subscribe to threshold-based AQI alerts via SendGrid |
| 📥 **Export** | Download data as CSV or auto-generated PDF report |
| ⚡ **FastAPI Backend** | Full REST API with auto-docs at `/docs` |

---

## 🏗️ Architecture

```
AQICN API ────────────┐
OpenWeatherMap API ───┤  asyncio ingestion  ┌──── SQLite / Supabase
TomTom Traffic API ───┘  (every 5 minutes)  │
                                             ▼
                              Feature Engineering (Pandas)
                                    + Anomaly Detection
                                             │
                               ┌─────────────┴──────────────┐
                           XGBoost                      Prophet
                         (multivariate)              (time-series)
                               └─────────────┬──────────────┘
                                             │
                                    FastAPI REST API
                                             │
                                   Streamlit Dashboard
```

---

## 🚀 Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/YOUR_USERNAME/vizag-dashboard.git
cd vizag-dashboard
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env and fill in your API keys:
```

| Key | Where to get it | Cost |
|-----|-----------------|------|
| `AQICN_TOKEN` | [aqicn.org/data-platform/token](https://aqicn.org/data-platform/token/) | Free |
| `OWM_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) | Free |
| `TOMTOM_API_KEY` | [developer.tomtom.com](https://developer.tomtom.com/) | Free (no CC) |

> **No API keys?** The system runs in **demo mode** — simulated traffic data, AQICN `demo` token (Vizag data), and Prophet-only predictions.

### 3. Seed Historical Data & Train Models

```bash
python scripts/seed_historical.py     # Generates 30 days of synthetic data
python scripts/train_model.py         # Trains XGBoost + Prophet + Anomaly Detector
```

### 4. Start the API

```bash
uvicorn api.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 5. Launch the Dashboard

```bash
streamlit run dashboard/app.py
# Dashboard: http://localhost:8501
```

---

## 📡 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/live/aqi` | GET | Latest AQI + pollutants + anomaly flag |
| `/api/live/traffic` | GET | Latest traffic congestion + speed |
| `/api/live/stats` | GET | Traffic↔AQI correlation statistics |
| `/api/predict/next-hour` | GET | XGBoost/Prophet 1-hour AQI prediction |
| `/api/predict/next/{n}` | GET | Multi-hour AQI forecast (1–24h) |
| `/api/history/aqi` | GET | Paginated AQI history |
| `/api/history/export/csv` | GET | Download merged dataset as CSV |
| `/api/history/export/pdf` | GET | Download PDF summary report |
| `/api/alerts/subscribe` | POST | Subscribe to email AQI alerts |
| `/api/alerts/unsubscribe` | DELETE | Unsubscribe email |

Full interactive docs: `http://localhost:8000/docs`

---

## 🧪 Testing

```bash
pytest tests/ -v
```

---

## 📊 ML Models

### XGBoost (Primary)
- **Features**: 24 features including lag AQI, pollutants, weather, traffic congestion
- **Target**: AQI at T+1 hour
- **Training**: 720 hours (30 days) of historical data
- **Retraining**: Automatic every 6 hours

### Prophet (Baseline)
- **Input**: Hourly AQI time series
- **Output**: Next 1–24 hours with 90% confidence interval
- **Advantage**: Decomposes daily + weekly seasonality (great for visualization)

### Anomaly Detection (IsolationForest)
- **Contamination**: 5% expected anomaly rate
- **Features**: AQI, PM2.5, PM10, NO₂, humidity, temperature
- **Fallback**: Threshold rule (AQI > 300) when no model is trained

---

## 🌐 Deployment

### Backend (Render)
```bash
# render.yaml
services:
  - type: web
    name: vizag-api
    runtime: python
    buildCommand: "pip install -r requirements.txt && python scripts/seed_historical.py && python scripts/train_model.py"
    startCommand: "uvicorn api.main:app --host 0.0.0.0 --port $PORT"
```

### Dashboard (Streamlit Cloud)
1. Push repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Set main file: `dashboard/app.py`
4. Add secrets (API keys) in the Streamlit Cloud dashboard

---

## 💡 Assumptions

1. **Single CPCB station**: Vizag has one official CAAQM station (Dwarakanagar/GVMC). OWM provides a satellite-model fallback for station downtime.
2. **AQI scale**: US-EPA 0–500. OWM's 1–5 scale is mapped to approximate US-EPA midpoints.
3. **Traffic proxy**: TomTom flow data is averaged across 5 key Vizag junctions to approximate city-wide congestion.
4. **Kafka not used**: asyncio polling (5 min) is sufficient for this data velocity and keeps the repo under 10 MB.
5. **Prophet + XGBoost**: LSTM is not included (GPU not needed for hackathon scale; XGBoost is equally accurate).

---

## 📁 Project Structure

```
vizag-dashboard/
├── config.py                  # Centralised settings (Pydantic)
├── requirements.txt
├── .env.example
├── ingestion/
│   ├── aqi_collector.py       # AQICN + OWM fetchers
│   ├── traffic_collector.py   # TomTom traffic fetcher
│   ├── scheduler.py           # asyncio periodic polling
│   └── database.py            # SQLAlchemy async ORM
├── processing/
│   ├── feature_engineering.py # ML feature pipeline
│   └── anomaly_detection.py   # IsolationForest detector
├── ml/
│   ├── predictor.py           # Unified XGBoost + Prophet interface
│   └── models/                # Saved model artifacts (.pkl)
├── api/
│   ├── main.py                # FastAPI app
│   └── routes/
│       ├── live.py            # Live data endpoints
│       ├── predict.py         # Prediction endpoints
│       ├── history.py         # History + export
│       └── alerts.py          # Email alert subscriptions
├── dashboard/
│   └── app.py                 # Streamlit dashboard
├── scripts/
│   ├── seed_historical.py     # Synthetic data generator
│   └── train_model.py         # Model training CLI
└── tests/
    ├── test_ingestion.py
    └── test_api.py
```

---

## 🔐 Security Best Practices

- **Never commit `.env`** — it's in `.gitignore`
- **API keys in environment variables only** — loaded via `pydantic-settings`
- **Rate limiting**: Add `slowapi` middleware in production
- **Admin endpoints**: `/api/alerts/subscribers` should be protected with Supabase JWT in production
- **HTTPS**: Always use HTTPS in production (Render/Railway handle this automatically)

---

## 📜 License

MIT License — See [LICENSE](LICENSE)

---

*Built with ❤️ for Visakhapatnam · Data from AQICN, OpenWeatherMap & TomTom*
