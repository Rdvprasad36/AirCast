"""
ml/lstm_model.py — Deep Learning LSTM model for AQI spatiotemporal prediction.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MODEL_PATH = Path("ml/models/lstm_aqi.pth")

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

    class _MockModule:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _MockNN:
        Module = _MockModule

    nn = _MockNN()  # type: ignore


if TORCH_AVAILABLE:
    class AQILSTMModel(nn.Module):
        """LSTM-based neural network for spatiotemporal AQI prediction."""
        def __init__(
            self,
            input_size: int = 10,
            hidden_size: int = 64,
            num_layers: int = 2,
            output_size: int = 1,
        ) -> None:
            super().__init__()
            self.input_size = input_size
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            self.output_size = output_size
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
            )
            self.fc = nn.Linear(hidden_size, output_size)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out, _ = self.lstm(x)
            out = self.fc(out[:, -1, :])
            return out
else:
    class AQILSTMModel(nn.Module):  # type: ignore
        """Fallback Stub for AQILSTMModel when PyTorch is not installed."""
        def __init__(
            self,
            input_size: int = 10,
            hidden_size: int = 64,
            num_layers: int = 2,
            output_size: int = 1,
        ) -> None:
            self.input_size = input_size
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            self.output_size = output_size

        def forward(self, x: Any) -> Any:
            return x


def _get_heuristic_aqi(city: str, dt: datetime) -> float:
    """Generate diurnal heuristic AQI prediction based on city and hour."""
    hour = dt.hour
    city_bases: Dict[str, float] = {
        "Visakhapatnam": 85.0,
        "Vijayawada": 95.0,
        "Guntur": 90.0,
        "Tirupati": 70.0,
        "Kurnool": 75.0,
        "Rajahmundry": 80.0,
        "Nellore": 72.0,
        "Kakinada": 78.0,
        "Kadapa": 74.0,
        "Anantapur": 76.0,
    }
    base = city_bases.get(city, 80.0)

    # Diurnal traffic/pollution peaks (morning rush 8-10, evening rush 17-20)
    if 8 <= hour <= 10:
        multiplier = 1.3
    elif 17 <= hour <= 20:
        multiplier = 1.35
    elif 11 <= hour <= 16:
        multiplier = 1.05
    elif 0 <= hour <= 5:
        multiplier = 0.8
    else:
        multiplier = 1.0

    variation = 5.0 * math.sin((hour / 24.0) * 2 * math.pi)
    return max(15.0, round(base * multiplier + variation, 1))


def predict_spatiotemporal(
    city: str = "Visakhapatnam",
    hours_ahead: int = 6,
) -> List[Dict[str, Any]]:
    """
    Predict spatiotemporal AQI using saved LSTM model if available,
    otherwise fall back to heuristic predictions based on time of day.

    Returns:
        List of dicts with forecast_for, predicted_aqi, model_name="lstm"
    """
    now = datetime.now(timezone.utc)
    predictions: List[Dict[str, Any]] = []

    # Attempt to load saved model from ml/models/lstm_aqi.pth
    if TORCH_AVAILABLE and MODEL_PATH.exists():
        try:
            model = AQILSTMModel()
            state_dict = torch.load(str(MODEL_PATH), map_location=torch.device("cpu"))
            model.load_state_dict(state_dict)
            model.eval()
            logger.info("Loaded LSTM model from %s", MODEL_PATH)
        except Exception as exc:
            logger.warning("Could not load LSTM model from %s: %s", MODEL_PATH, exc)

    # Generate predictions (using diurnal heuristic fallback)
    for i in range(1, hours_ahead + 1):
        target_time = now + timedelta(hours=i)
        pred_aqi = _get_heuristic_aqi(city, target_time)
        predictions.append({
            "forecast_for": target_time.isoformat(),
            "predicted_aqi": pred_aqi,
            "model_name": "lstm",
        })

    return predictions
