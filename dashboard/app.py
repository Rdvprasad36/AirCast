"""
dashboard/app.py — Streamlit main dashboard.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │  Header: Vizag Traffic & Pollution Dashboard        │
  ├──────────┬──────────┬──────────┬────────────────────┤
  │  AQI     │ Traffic  │ Pred.    │  Anomaly Count     │
  │  Card    │ Card     │ Card     │  Card              │
  ├──────────┴──────────┴──────────┴────────────────────┤
  │  Left: Interactive Folium Map (traffic heatmap)     │
  │  Right: Real-time AQI trend chart (Plotly)          │
  ├─────────────────────────────────────────────────────┤
  │  Bottom: Hourly Forecast Chart + Pollutant Breakdown│
  ├─────────────────────────────────────────────────────┤
  │  Alerts: Subscribe Panel + Alert Log                │
  └─────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="Vizag Traffic & Pollution Dashboard",
    page_icon="🌫️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Config ─────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"
AUTO_REFRESH_SECONDS = 300  # 5 minutes

VIZAG_LAT, VIZAG_LON = 17.6868, 83.2185

AQI_COLORS = {
    "Good": "#00e400",
    "Moderate": "#ffff00",
    "Unhealthy for Sensitive Groups": "#ff7e00",
    "Unhealthy": "#ff0000",
    "Very Unhealthy": "#8f3f97",
    "Hazardous": "#7e0023",
}


# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: #0d1117;
    color: #e6edf3;
  }

  /* Header gradient */
  .dashboard-header {
    background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 50%, #1a2332 100%);
    border-bottom: 1px solid #30363d;
    padding: 1.5rem 2rem;
    margin: -1rem -1rem 1.5rem -1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .dashboard-header h1 {
    font-size: 1.75rem;
    font-weight: 900;
    background: linear-gradient(135deg, #58a6ff, #3fb950, #f78166);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
  }

  /* Metric cards */
  .metric-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
    transition: border-color 0.2s, transform 0.2s;
    position: relative;
    overflow: hidden;
  }
  .metric-card:hover {
    border-color: #58a6ff;
    transform: translateY(-2px);
  }
  .metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--card-accent, #58a6ff);
    border-radius: 12px 12px 0 0;
  }
  .metric-value {
    font-size: 2.5rem;
    font-weight: 900;
    line-height: 1;
    margin: 0.5rem 0 0.25rem;
  }
  .metric-label {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
  .metric-sublabel {
    font-size: 0.9rem;
    font-weight: 600;
    margin-top: 0.25rem;
  }

  /* Anomaly badge */
  .anomaly-badge {
    display: inline-block;
    background: #da3633;
    color: white;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  /* Alert banner */
  .alert-banner {
    background: linear-gradient(135deg, rgba(218, 54, 51, 0.15), rgba(218, 54, 51, 0.05));
    border: 1px solid #da3633;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  /* Plotly chart background override */
  .js-plotly-plot .plotly .modebar {
    background: transparent !important;
  }

  /* Section titles */
  .section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #21262d;
  }

  /* Hide Streamlit branding */
  #MainMenu, footer, header { visibility: hidden; }
  .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)


# ── API Helpers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_live_aqi(city: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/api/live/aqi?city={city}", timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=60)
def fetch_live_traffic(city: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/api/live/traffic?city={city}", timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=300)
def fetch_prediction(city: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/api/predict/next-hour?city={city}", timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=300)
def fetch_forecast(city: str, n: int = 6) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/api/predict/next/{n}?city={city}", timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=120)
def fetch_aqi_history(city: str, hours: int = 24) -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/api/history/aqi?hours={hours}&limit=500&city={city}", timeout=10)
        return r.json().get("readings", []) if r.status_code == 200 else []
    except Exception:
        return []


@st.cache_data(ttl=120)
def fetch_stats(city: str, hours: int = 24) -> dict:
    try:
        r = requests.get(f"{API_BASE}/api/live/stats?hours={hours}&city={city}", timeout=5)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


def fetch_citizen_reports(city: str, limit: int = 50) -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/api/reports/?limit={limit}&city={city}", timeout=5)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []



def submit_citizen_report(data: dict) -> bool:
    try:
        r = requests.post(f"{API_BASE}/api/reports/", json=data, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def fetch_insight(city: str) -> str:
    try:
        r = requests.get(f"{API_BASE}/api/insights/root-cause?city={city}", timeout=5)
        if r.status_code == 200:
            return r.json().get("insight", "No insights available right now.")
    except Exception:
        pass
    return "No insights available right now."
# ── Map Builder ─────────────────────────────────────────────────────────────

def build_traffic_map(traffic: dict | None, reports: list[dict] = None) -> object:
    """Build Folium map with traffic congestion overlay and citizen reports."""
    import folium
    from folium.plugins import HeatMap

    congestion = traffic.get("congestion_index", 0.3) if traffic else 0.3
    color = "#00e400" if congestion < 0.3 else "#ff7e00" if congestion < 0.6 else "#ff0000"

    m = folium.Map(
        location=[VIZAG_LAT, VIZAG_LON],
        zoom_start=13,
        tiles="CartoDB.DarkMatter",
    )

    # Monitoring points
    monitoring_points = [
        (17.6868, 83.2185, "Dwarakanagar"),
        (17.7231, 83.3012, "Steel Plant Road"),
        (17.7120, 83.2237, "Jagadamba Junction"),
        (17.6540, 83.2170, "NAD Junction"),
        (17.7420, 83.3310, "Gajuwaka"),
    ]

    for lat, lon, label in monitoring_points:
        # Simulate per-point congestion with slight variation
        import random
        random.seed(hash(label) % 1000)
        pt_congestion = max(0, min(1, congestion + random.uniform(-0.15, 0.15)))
        pt_color = "#00e400" if pt_congestion < 0.3 else "#ff7e00" if pt_congestion < 0.6 else "#ff0000"

        folium.CircleMarker(
            location=[lat, lon],
            radius=12,
            color=pt_color,
            fill=True,
            fill_color=pt_color,
            fill_opacity=0.7,
            popup=folium.Popup(
                f"""<div style='font-family:sans-serif;min-width:150px'>
                <b>{label}</b><br>
                Congestion: {pt_congestion:.0%}<br>
                Speed: ~{(1-pt_congestion)*60:.0f} km/h
                </div>""",
                max_width=200,
            ),
            tooltip=f"{label}: {pt_congestion:.0%} congestion",
        ).add_to(m)

    # Heat map layer based on congestion
    heat_data = [
        [lat + (i * 0.002), lon + (j * 0.002), congestion]
        for lat, lon, _ in monitoring_points
        for i in range(-3, 4)
        for j in range(-3, 4)
    ]
    HeatMap(
        heat_data,
        radius=20,
        blur=15,
        min_opacity=0.3,
        gradient={0.4: "blue", 0.65: "orange", 1: "red"},
    ).add_to(m)

    # AQI station marker
    folium.Marker(
        location=[VIZAG_LAT, VIZAG_LON],
        popup=f"CPCB AQI Station\nDwarakanagar, Vizag",
        icon=folium.Icon(color="purple", icon="cloud", prefix="fa"),
        tooltip="AQI Monitoring Station",
    ).add_to(m)

    # Citizen Reports
    if reports:
        for r in reports:
            folium.Marker(
                location=[r["latitude"], r["longitude"]],
                popup=folium.Popup(f"<b>{r['issue_type']}</b><br>Severity: {r['severity']}/5<br>{r.get('description', '')}", max_width=250),
                icon=folium.Icon(color="red", icon="exclamation-circle", prefix="fa"),
                tooltip=r["issue_type"],
            ).add_to(m)

    return m


# ── Chart Builders ──────────────────────────────────────────────────────────

def build_aqi_trend_chart(history: list[dict]) -> go.Figure:
    """Build real-time AQI trend line chart."""
    if not history:
        fig = go.Figure()
        fig.add_annotation(text="No data yet", showarrow=False, font=dict(size=14, color="#8b949e"))
        return _style_chart(fig)

    df = pd.DataFrame(history)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    fig = go.Figure()

    # AQI fill zones (reference bands)
    for y0, y1, color, label in [
        (0, 50, "rgba(0,228,0,0.08)", "Good"),
        (50, 100, "rgba(255,255,0,0.08)", "Moderate"),
        (100, 150, "rgba(255,126,0,0.08)", "USG"),
        (150, 200, "rgba(255,0,0,0.08)", "Unhealthy"),
        (200, 300, "rgba(143,63,151,0.08)", "Very Unhealthy"),
    ]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=color, line_width=0, annotation_text=label,
                      annotation_position="left", annotation_font_size=9,
                      annotation_font_color="#8b949e")

    # Anomaly markers
    anomalies = df[df.get("is_anomaly", pd.Series([False] * len(df)))]
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies["timestamp"], y=anomalies["aqi"],
            mode="markers", name="Anomaly",
            marker=dict(symbol="x", size=14, color="#ff6b6b", line=dict(width=2)),
        ))

    # Main AQI line
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["aqi"],
        mode="lines+markers",
        name="AQI",
        line=dict(color="#58a6ff", width=2.5, shape="spline"),
        marker=dict(size=4),
        fill="tozeroy",
        fillcolor="rgba(88, 166, 255, 0.08)",
        hovertemplate="<b>%{y:.0f}</b> AQI<br>%{x|%H:%M}<extra></extra>",
    ))

    # PM2.5 overlay
    if "pm25" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["timestamp"], y=df["pm25"],
            mode="lines", name="PM2.5",
            line=dict(color="#f78166", width=1.5, dash="dot"),
            hovertemplate="<b>%{y:.1f}</b> PM2.5<br>%{x|%H:%M}<extra></extra>",
        ))

    fig.update_layout(
        yaxis_title="AQI / PM2.5",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return _style_chart(fig, title="Real-Time AQI Trend")


def build_forecast_chart(forecast: dict | None) -> go.Figure:
    """Build 6-hour forecast chart with confidence bands."""
    fig = go.Figure()

    if not forecast or not forecast.get("predictions"):
        fig.add_annotation(text="Forecast unavailable", showarrow=False,
                           font=dict(size=14, color="#8b949e"))
        return _style_chart(fig, title="6-Hour AQI Forecast")

    preds = forecast["predictions"]
    times = [pd.to_datetime(p["forecast_for"]) for p in preds]
    values = [p["predicted_aqi"] for p in preds]
    lowers = [p["confidence_lower"] for p in preds]
    uppers = [p["confidence_upper"] for p in preds]

    # Confidence band
    fig.add_trace(go.Scatter(
        x=times + times[::-1],
        y=uppers + lowers[::-1],
        fill="toself",
        fillcolor="rgba(88,166,255,0.15)",
        line=dict(color="rgba(255,255,255,0)"),
        name="90% CI",
        hoverinfo="skip",
    ))

    # Forecast line
    fig.add_trace(go.Scatter(
        x=times, y=values,
        mode="lines+markers+text",
        name="Predicted AQI",
        line=dict(color="#3fb950", width=3, shape="spline"),
        marker=dict(size=8, color="#3fb950"),
        text=[f"{v:.0f}" for v in values],
        textposition="top center",
        textfont=dict(size=11, color="#3fb950"),
        hovertemplate="<b>%{y:.0f}</b> AQI<br>%{x|%H:%M}<extra></extra>",
    ))

    return _style_chart(fig, title=f"6-Hour AQI Forecast ({preds[0]['model_used']})")


def build_pollutant_chart(history: list[dict]) -> go.Figure:
    """Build a bar chart of average pollutant concentrations."""
    fig = go.Figure()

    if not history:
        return _style_chart(fig, title="Pollutant Breakdown")

    df = pd.DataFrame(history)
    pollutants = {
        "PM2.5 (μg/m³)": ("pm25", "#f78166"),
        "PM10 (μg/m³)": ("pm10", "#d2a8ff"),
        "NO₂ (ppb)": ("no2", "#ffa657"),
        "O₃ (ppb)": ("o3", "#79c0ff"),
    }

    cats, vals, colors = [], [], []
    for label, (col, color) in pollutants.items():
        if col in df.columns and df[col].notna().any():
            cats.append(label)
            vals.append(df[col].mean())
            colors.append(color)

    if cats:
        fig.add_trace(go.Bar(
            x=cats, y=vals, marker_color=colors,
            text=[f"{v:.1f}" for v in vals],
            textposition="outside",
            hovertemplate="<b>%{y:.1f}</b> %{x}<extra></extra>",
        ))

    return _style_chart(fig, title="Average Pollutant Levels (24h)")


def _style_chart(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply consistent dark-mode styling to all charts."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#8b949e", family="Inter"), x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#e6edf3"),
        margin=dict(l=40, r=20, t=40, b=40),
        xaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d", showline=False),
        yaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d", showline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#30363d"),
        hovermode="x unified",
    )
    return fig


# ── Main Render ─────────────────────────────────────────────────────────────

def main():
    # ── Sidebar controls ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Dashboard Settings")
        selected_city = st.selectbox("Select City", ["Visakhapatnam", "Vijayawada", "Guntur", "Tirupati", "Nellore", "Kurnool"])
        
    # ── Header ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="dashboard-header">
      <span style="font-size:2.5rem">🌫️</span>
      <div>
        <h1>{selected_city} Traffic & Pollution Dashboard</h1>
        <div style="color:#8b949e;font-size:0.8rem">
          Andhra Pradesh, India &nbsp;|&nbsp;
          Live data · Real-time predictions · Anomaly alerts
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        history_hours = st.selectbox("History window", [6, 12, 24, 48, 168], index=2,
                                     format_func=lambda h: f"{h}h" if h < 48 else f"{h//24}d")
        forecast_hours = st.slider("Forecast horizon", 1, 24, 6)
        auto_refresh = st.checkbox("Auto-refresh (5 min)", value=True)

        st.markdown("---")
        st.markdown("### 🔔 Subscribe to Alerts")
        with st.form("subscribe_form"):
            sub_name = st.text_input("Your name")
            sub_email = st.text_input("Email address")
            sub_threshold = st.slider("Alert when AQI exceeds", 50, 300, 100)
            if st.form_submit_button("Subscribe"):
                try:
                    r = requests.post(
                        f"{API_BASE}/api/alerts/subscribe",
                        json={"email": sub_email, "name": sub_name, "threshold_aqi": sub_threshold},
                        timeout=5,
                    )
                    if r.status_code == 200:
                        st.success("✅ Subscribed!")
                    else:
                        st.error(f"Failed: {r.text}")
                except Exception as e:
                    st.error(f"Could not connect to API: {e}")

        st.markdown("---")
        st.markdown("### 📢 Report an Issue")
        with st.form("report_form"):
            issue_type = st.selectbox("Issue Type", ["Heavy Traffic", "Construction Dust", "Industrial Emissions", "Other"])
            severity = st.slider("Severity", 1, 5, 3)
            desc = st.text_input("Description (optional)")
            lat = st.number_input("Latitude", value=VIZAG_LAT, format="%.4f")
            lon = st.number_input("Longitude", value=VIZAG_LON, format="%.4f")
            
            if st.form_submit_button("Submit Report"):
                report_data = {
                    "city_name": selected_city,
                    "latitude": lat,
                    "longitude": lon,
                    "issue_type": issue_type,
                    "description": desc,
                    "severity": severity
                }
                if submit_citizen_report(report_data):
                    st.success("✅ Report submitted! Thank you.")
                    st.cache_data.clear() # Refresh map
                else:
                    st.error("Failed to submit report.")

        st.markdown("---")
        st.markdown("### 📥 Export Data")
        col1, col2 = st.columns(2)
        with col1:
            st.link_button("CSV", f"{API_BASE}/api/history/export/csv?hours={history_hours}")
        with col2:
            st.link_button("PDF", f"{API_BASE}/api/history/export/pdf?hours={history_hours}")

    # ── Fetch all data ─────────────────────────────────────────────────
    aqi_data = fetch_live_aqi(selected_city)
    traffic_data = fetch_live_traffic(selected_city)
    prediction = fetch_prediction(selected_city)
    forecast = fetch_forecast(selected_city, forecast_hours)
    history = fetch_aqi_history(selected_city, history_hours)
    stats = fetch_stats(selected_city, history_hours)
    reports = fetch_citizen_reports(selected_city, limit=20)

    # ── Anomaly alert banner ───────────────────────────────────────────
    if aqi_data and aqi_data.get("is_anomaly"):
        st.markdown("""
        <div class="alert-banner">
          <span style="font-size:1.5rem">🚨</span>
          <div>
            <strong style="color:#ff6b6b">Anomaly Detected!</strong>
            Unusual AQI spike detected — may indicate a local pollution event.
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Metric Cards ───────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        aqi_val = aqi_data["aqi"] if aqi_data else "—"
        aqi_cat = aqi_data.get("category", "") if aqi_data else ""
        aqi_color = aqi_data.get("color", "#58a6ff") if aqi_data else "#58a6ff"
        anomaly_html = '<span class="anomaly-badge">⚠ ANOMALY</span>' if (aqi_data and aqi_data.get("is_anomaly")) else ""
        st.markdown(f"""
        <div class="metric-card" style="--card-accent:{aqi_color}">
          <div class="metric-label">Current AQI</div>
          <div class="metric-value" style="color:{aqi_color}">{aqi_val if isinstance(aqi_val, str) else f'{aqi_val:.0f}'}</div>
          <div class="metric-sublabel">{aqi_cat}</div>
          {anomaly_html}
        </div>
        """, unsafe_allow_html=True)

    with c2:
        ci = traffic_data.get("congestion_index", 0) if traffic_data else 0
        ci_label = traffic_data.get("congestion_label", "—") if traffic_data else "—"
        spd = traffic_data.get("current_speed_kmh", 0) if traffic_data else 0
        ci_color = "#00e400" if ci < 0.3 else "#ff7e00" if ci < 0.6 else "#ff0000"
        st.markdown(f"""
        <div class="metric-card" style="--card-accent:{ci_color}">
          <div class="metric-label">Traffic Congestion</div>
          <div class="metric-value" style="color:{ci_color}">{ci:.0%}</div>
          <div class="metric-sublabel">{ci_label} · {spd:.0f} km/h</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        pred_val = prediction.get("predicted_aqi", "—") if prediction else "—"
        pred_cat = prediction.get("category", "") if prediction else ""
        pred_color = prediction.get("color", "#3fb950") if prediction else "#3fb950"
        model_used = prediction.get("model_used", "—") if prediction else "—"
        st.markdown(f"""
        <div class="metric-card" style="--card-accent:{pred_color}">
          <div class="metric-label">Predicted AQI (+1h)</div>
          <div class="metric-value" style="color:{pred_color}">{pred_val if isinstance(pred_val, str) else f'{pred_val:.0f}'}</div>
          <div class="metric-sublabel">{pred_cat}</div>
          <div style="font-size:0.7rem;color:#8b949e;margin-top:4px">Model: {model_used}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        anomaly_count = stats.get("anomaly_count", 0)
        corr = stats.get("traffic_aqi_correlation")
        corr_str = f"{corr:+.2f}" if corr is not None else "—"
        st.markdown(f"""
        <div class="metric-card" style="--card-accent:#d2a8ff">
          <div class="metric-label">Anomalies ({history_hours}h)</div>
          <div class="metric-value" style="color:#d2a8ff">{anomaly_count}</div>
          <div class="metric-sublabel">Traffic↔AQI r={corr_str}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Map + AQI Trend ────────────────────────────────────────────────
    map_col, chart_col = st.columns([1, 1])

    with map_col:
        st.markdown('<div class="section-title">🗺️ Live Traffic Heatmap — Vizag</div>', unsafe_allow_html=True)
        traffic_map = build_traffic_map(traffic_data, reports)
        st_folium(traffic_map, width=None, height=380, returned_objects=[])


    with chart_col:
        st.markdown('<div class="section-title">📈 Real-Time AQI Trend</div>', unsafe_allow_html=True)
        st.plotly_chart(
            build_aqi_trend_chart(history),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Forecast + Pollutants ──────────────────────────────────────────
    fc_col, poll_col = st.columns([1, 1])

    with fc_col:
        st.markdown(f'<div class="section-title">🔮 {forecast_hours}-Hour AQI Forecast</div>', unsafe_allow_html=True)
        st.plotly_chart(
            build_forecast_chart(forecast),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with poll_col:
        st.markdown('<div class="section-title">🧪 Pollutant Breakdown</div>', unsafe_allow_html=True)
        st.plotly_chart(
            build_pollutant_chart(history),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Stats footer ───────────────────────────────────────────────────
    ts = aqi_data.get("timestamp", "") if aqi_data else ""
    source = aqi_data.get("source", "—") if aqi_data else "—"
    st.markdown(f"""
    <div style="text-align:center;color:#8b949e;font-size:0.75rem;padding:1rem 0;border-top:1px solid #21262d;margin-top:1rem">
      Last update: {ts[:19].replace("T"," ")} UTC &nbsp;|&nbsp;
      Source: {source.upper()} &nbsp;|&nbsp;
      Auto-refresh: {'ON (5 min)' if auto_refresh else 'OFF'} &nbsp;|&nbsp;
      <a href="{API_BASE}/docs" style="color:#58a6ff">API Docs</a>
    </div>
    """, unsafe_allow_html=True)

    # ── Auto-refresh ───────────────────────────────────────────────────
    if auto_refresh:
        time.sleep(AUTO_REFRESH_SECONDS)
        st.cache_data.clear()
        st.rerun()


if __name__ == "__main__":
    main()
