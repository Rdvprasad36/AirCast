"""
scripts/train_model.py — Train XGBoost + Prophet models from DB data.

Run this once after seeding historical data (or after ~24h of live collection).

Usage:
  python scripts/train_model.py
  python scripts/train_model.py --hours 168     # last week only
  python scripts/train_model.py --model xgboost # only XGBoost
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("data", exist_ok=True)
os.makedirs("ml/models", exist_ok=True)


async def main(hours: int, model: str) -> None:
    from processing.feature_engineering import load_training_data
    from ml.predictor import train_xgboost, train_prophet
    from processing.anomaly_detection import train_anomaly_detector

    print(f"📊 Loading training data (last {hours} hours)...")
    df = await load_training_data(hours_back=hours)

    if df.empty:
        print("❌ No data found. Run `python scripts/seed_historical.py` first.")
        return

    print(f"   Loaded {len(df)} rows, {len(df.columns)} features.")

    if model in ("xgboost", "all"):
        print("\n🤖 Training XGBoost...")
        try:
            train_xgboost(df)
            print("   ✅ XGBoost model saved → ml/models/xgboost_aqi.pkl")
        except Exception as e:
            print(f"   ❌ XGBoost training failed: {e}")

    if model in ("prophet", "all"):
        print("\n📈 Training Prophet...")
        try:
            train_prophet(df)
            print("   ✅ Prophet model saved → ml/models/prophet_aqi.pkl")
        except Exception as e:
            print(f"   ❌ Prophet training failed: {e}")

    if model in ("anomaly", "all"):
        print("\n🔍 Training Anomaly Detector...")
        try:
            train_anomaly_detector(df)
            print("   ✅ Anomaly detector saved → ml/models/anomaly_detector.pkl")
        except Exception as e:
            print(f"   ❌ Anomaly detector training failed: {e}")

    print("\n🎉 Training complete! Models ready for serving.")
    print("   Start the API: uvicorn api.main:app --reload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train ML models for Vizag Dashboard")
    parser.add_argument("--hours", type=int, default=720, help="Hours of history to use (default: 720 = 30 days)")
    parser.add_argument("--model", choices=["all", "xgboost", "prophet", "anomaly"], default="all")
    args = parser.parse_args()

    asyncio.run(main(args.hours, args.model))
