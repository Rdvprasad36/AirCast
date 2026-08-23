# Vizag Traffic & Pollution Dashboard (AirCast) 🌫️

An enterprise-grade, cloud-native Smart City platform designed to monitor, forecast, and analyze real-time air quality and traffic congestion across Andhra Pradesh (Visakhapatnam, Vijayawada, Guntur, Tirupati, Nellore, Kurnool).

## 🚀 Features

- **Real-Time Data Ingestion:** Automated async pipelines fetching data from AQICN, OpenWeatherMap, and TomTom APIs.
- **Machine Learning Forecasting:** PyTorch LSTM and XGBoost models to predict spatial-temporal pollution levels 6-24 hours into the future.
- **Automated Root Cause Analysis:** AI-powered anomaly detection that generates plain-English insights (e.g., "AQI spiked due to 15% higher traffic and stagnant winds").
- **Crowdsourced Citizen Reporting:** Local citizens can report heavy dust, traffic jams, or industrial emissions directly via the dashboard.
- **Smart Traffic Re-routing:** Algorithms that suggest alternative travel routes to reduce exposure to heavily polluted zones.
- **Multi-Channel Alerts:** Twilio SMS, WhatsApp, and SendGrid Email notifications triggered when AQI crosses hazardous thresholds.
- **Cross-Platform:** A beautiful web dashboard built with Streamlit and a dedicated mobile app skeleton built in React Native/Expo.
- **Cloud-Native Architecture:** Fully Dockerized, powered by FastAPI, SQLAlchemy, PostgreSQL (Supabase ready), and Redis.

## 🛠️ Tech Stack
- **Backend:** Python 3.13, FastAPI, SQLAlchemy (Async), Uvicorn
- **Frontend (Web):** Streamlit, Plotly, Folium Maps
- **Frontend (Mobile):** React Native, Expo
- **Machine Learning:** PyTorch, scikit-learn, XGBoost
- **Database:** PostgreSQL (Supabase) / SQLite (Dev)
- **Infrastructure:** Docker, Docker Compose

## 📦 How to Run (Local Development)

1. **Clone & Setup Environment**
   `ash
   git clone https://github.com/Rdvprasad36/AirCast.git
   cd AirCast
   python -m venv venv
   source venv/bin/activate  # Or .\venv\Scripts\activate on Windows
   pip install -r requirements.txt
   `

2. **Configure Environment Variables**
   Create a .env file based on .env.example and add your API keys (AQICN, TomTom, Twilio, Supabase URL).

3. **Seed Database**
   Populate your database with 30 days of historical smart-city data:
   `ash
   python scripts/seed_historical.py
   `

4. **Start the Platform**
   Start the FastAPI backend and Streamlit dashboard:
   `ash
   uvicorn api.main:app --reload --port 8000
   streamlit run dashboard/app.py
   `
   *Dashboard available at http://localhost:8501*

## 📱 Running the Mobile App
1. Install Expo: 
pm install -g expo-cli
2. Navigate to mobile/ and run 
pm install
3. Run 
px expo start and scan the QR code with the Expo Go app.

## 🧠 Why We Built This (AirCast)
Urban pollution is a massive hidden health crisis, exacerbated by unmanaged traffic flow and industrial emissions. AirCast provides municipal authorities and citizens with actionable intelligence. By correlating wind vectors, local events, and traffic density, we don't just show *what* the AQI is—we explain *why* it's happening and *how* to avoid it.
