"""
tests/test_ingestion.py — Unit tests for data collection modules.
"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAQICollector:
    """Tests for AQICN + OWM response parsing."""

    def test_owm_aqi_map_coverage(self):
        """All OWM AQI index values (1-5) must map to US-EPA equivalent."""
        from ingestion.aqi_collector import OWM_AQI_MAP
        for i in range(1, 6):
            assert i in OWM_AQI_MAP, f"OWM AQI index {i} missing from map"
            assert 0 < OWM_AQI_MAP[i] <= 500

    def test_simulate_traffic_returns_valid_data(self):
        """Simulated traffic data must include all required fields."""
        from ingestion.traffic_collector import _simulate_traffic
        result = _simulate_traffic()
        assert "current_speed" in result
        assert "free_flow_speed" in result
        assert result["current_speed"] > 0
        assert result["free_flow_speed"] > 0

    def test_congestion_index_calculation(self):
        """Congestion index should be between 0 and 1."""
        from ingestion.traffic_collector import _compute_congestion_index
        assert _compute_congestion_index(60, 60) == pytest.approx(0.0)
        assert _compute_congestion_index(0, 60) == pytest.approx(1.0)
        assert _compute_congestion_index(30, 60) == pytest.approx(0.5)
        # Edge case: free_flow = 0
        assert _compute_congestion_index(30, 0) == 0.0


class TestConfig:
    """Tests for application configuration."""

    def test_aqi_category_good(self):
        from config import settings
        cat, color = settings.aqi_category(25)
        assert cat == "Good"
        assert color == "#00e400"

    def test_aqi_category_hazardous(self):
        from config import settings
        cat, color = settings.aqi_category(400)
        assert cat == "Hazardous"
        assert color == "#7e0023"

    def test_aqi_category_boundary(self):
        from config import settings
        cat50, _ = settings.aqi_category(50)
        cat51, _ = settings.aqi_category(51)
        assert cat50 == "Good"
        assert cat51 == "Moderate"


class TestFeatureEngineering:
    """Tests for the feature engineering pipeline."""

    def test_build_feature_dataframe_temporal_features(self):
        """Temporal features must be correctly computed."""
        import pandas as pd
        from processing.feature_engineering import build_feature_dataframe

        timestamps = pd.date_range("2024-01-15 08:00", periods=50, freq="5min")
        aqi_df = pd.DataFrame({
            "timestamp": timestamps,
            "aqi": [80 + i * 0.1 for i in range(50)],
            "source": "test",
            "pm25": 45.0,
            "pm10": 30.0,
            "no2": 12.0,
            "o3": 20.0,
            "so2": 5.0,
            "co": 0.5,
            "humidity": 65.0,
            "temperature": 28.0,
            "wind_speed": 8.0,
            "category": "Moderate",
            "is_anomaly": False,
        })

        df = build_feature_dataframe(aqi_df, pd.DataFrame())
        assert "hour" in df.columns
        assert "is_weekend" in df.columns
        assert "is_peak_hour" in df.columns
        assert df["hour"].iloc[0] == 8

    def test_empty_aqi_raises(self):
        import pandas as pd
        from processing.feature_engineering import build_feature_dataframe
        with pytest.raises(ValueError, match="empty"):
            build_feature_dataframe(pd.DataFrame(), pd.DataFrame())


class TestAnomalyDetection:
    """Tests for the anomaly detection module."""

    def test_threshold_fallback_high_aqi(self):
        """Without a trained model, high AQI should be flagged."""
        from processing.anomaly_detection import is_anomaly
        from ingestion.database import AQIReading
        from datetime import datetime, timezone

        high_reading = AQIReading(
            aqi=350.0, pm25=200.0, pm10=150.0, no2=80.0,
            humidity=60.0, temperature=28.0,
            timestamp=datetime.now(timezone.utc),
            source="test", category="Hazardous",
        )
        # Without a model loaded, uses 300-threshold rule
        # AQI=350 > 300 → anomaly
        result = is_anomaly(high_reading)
        assert result is True

    def test_normal_aqi_not_anomaly(self):
        from processing.anomaly_detection import is_anomaly
        from ingestion.database import AQIReading
        from datetime import datetime, timezone

        normal_reading = AQIReading(
            aqi=75.0, pm25=40.0, pm10=25.0, no2=12.0,
            humidity=65.0, temperature=28.0,
            timestamp=datetime.now(timezone.utc),
            source="test", category="Moderate",
        )
        result = is_anomaly(normal_reading)
        assert result is False
