"""
analytics/ml_predictor.py
Trains a Random Forest model on historical sensor data and predicts
future AQI / PM2.5 values. Also provides trend analysis helpers.
"""

import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from models import SessionLocal, SensorReading, Prediction

MODEL_PATH = "data/aqi_model.pkl"
SCALER_PATH = "data/aqi_scaler.pkl"
MODEL_VERSION = "2.1"


# ──────────────────────────────────────────────
#  Feature Engineering
# ──────────────────────────────────────────────
def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create time-based and rolling features from raw sensor data."""
    df = df.copy()
    df["hour"]         = df["timestamp"].dt.hour
    df["day_of_week"]  = df["timestamp"].dt.dayofweek
    df["month"]        = df["timestamp"].dt.month
    df["is_weekend"]   = df["day_of_week"].isin([5, 6]).astype(int)
    df["hour_sin"]     = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"]     = np.cos(2 * np.pi * df["hour"] / 24)

    # Rolling stats (last 3 and 6 readings)
    for col in ["pm25", "pm10", "co", "no2", "o3", "temperature", "humidity"]:
        if col in df.columns:
            df[f"{col}_roll3"]  = df[col].rolling(3, min_periods=1).mean()
            df[f"{col}_roll6"]  = df[col].rolling(6, min_periods=1).mean()
            df[f"{col}_roll3_std"] = df[col].rolling(3, min_periods=1).std().fillna(0)

    return df


FEATURE_COLS = [
    "pm25", "pm10", "co", "no2", "o3", "co2", "temperature", "humidity",
    "hour", "day_of_week", "month", "is_weekend", "hour_sin", "hour_cos",
    "pm25_roll3", "pm25_roll6", "pm25_roll3_std",
    "pm10_roll3", "co_roll3", "no2_roll3", "temperature_roll3", "humidity_roll3",
]


# ──────────────────────────────────────────────
#  Model Training
# ──────────────────────────────────────────────
def train_model(node_id: Optional[str] = None) -> Dict:
    """
    Pull historical data from DB, engineer features, train RF model.
    Returns performance metrics.
    """
    db = SessionLocal()
    try:
        q = db.query(SensorReading)
        if node_id:
            q = q.filter_by(node_id=node_id)
        rows = q.order_by(SensorReading.timestamp).all()
    finally:
        db.close()

    if len(rows) < 50:
        logger.warning("[ML] Insufficient data for training (<50 records).")
        return {"error": "Insufficient data"}

    df = pd.DataFrame([r.to_dict() for r in rows])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["pm25", "pm10", "co", "no2", "o3", "co2", "aqi"])
    df = _build_features(df)

    available = [c for c in FEATURE_COLS if c in df.columns]
    X = df[available].fillna(0)
    y = df["aqi"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=5,
        learning_rate=0.05, subsample=0.8,
        random_state=42,
    )
    model.fit(X_train_s, y_train)
    preds = model.predict(X_test_s)

    mae  = mean_absolute_error(y_test, preds)
    r2   = r2_score(y_test, preds)

    os.makedirs("data", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "features": available, "version": MODEL_VERSION}, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    logger.info(f"[ML] Model trained – MAE={mae:.2f}  R²={r2:.3f}  samples={len(df)}")
    return {"mae": round(mae, 2), "r2": round(r2, 3), "samples": len(df), "version": MODEL_VERSION}


# ──────────────────────────────────────────────
#  Prediction
# ──────────────────────────────────────────────
def predict_aqi(node_id: str, hours_ahead: int = 24) -> List[Dict]:
    """
    Generate AQI forecasts for the next `hours_ahead` hours.
    Saves predictions to DB and returns a list of forecast dicts.
    """
    if not os.path.exists(MODEL_PATH):
        logger.warning("[ML] Model not trained yet.")
        return []

    with open(MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    model    = bundle["model"]
    features = bundle["features"]

    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    # Get recent readings for context
    db = SessionLocal()
    try:
        recent = (db.query(SensorReading)
                    .filter_by(node_id=node_id)
                    .order_by(SensorReading.timestamp.desc())
                    .limit(10).all())
    finally:
        db.close()

    if not recent:
        return []

    df_hist = pd.DataFrame([r.to_dict() for r in reversed(recent)])
    df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])
    df_hist = _build_features(df_hist)

    forecasts = []
    base_row  = df_hist.iloc[-1].copy()

    db = SessionLocal()
    try:
        for h in range(1, hours_ahead + 1):
            future_ts = datetime.utcnow() + timedelta(hours=h)
            row = base_row.copy()
            row["hour"]        = future_ts.hour
            row["day_of_week"] = future_ts.weekday()
            row["month"]       = future_ts.month
            row["is_weekend"]  = int(future_ts.weekday() in (5, 6))
            row["hour_sin"]    = np.sin(2 * np.pi * future_ts.hour / 24)
            row["hour_cos"]    = np.cos(2 * np.pi * future_ts.hour / 24)

            X = pd.DataFrame([row])[features].fillna(0)
            X_s = scaler.transform(X)
            pred_aqi = max(0, int(round(model.predict(X_s)[0])))

            # Confidence via ensemble spread (simple: use ±5% as proxy)
            confidence = max(0.60, min(0.99, 0.95 - h * 0.01))

            forecast = {
                "node_id":       node_id,
                "forecast_time": future_ts.isoformat(),
                "predicted_aqi": pred_aqi,
                "predicted_pm25": round(float(row.get("pm25", 0) * (pred_aqi / max(row.get("aqi", 1), 1))), 2),
                "confidence":    round(confidence, 2),
                "model_version": MODEL_VERSION,
            }
            forecasts.append(forecast)

            # Save
            p = Prediction(**forecast, created_at=datetime.utcnow())
            db.add(p)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[ML] Prediction save error: {e}")
    finally:
        db.close()

    return forecasts


# ──────────────────────────────────────────────
#  Trend Analysis
# ──────────────────────────────────────────────
def analyze_trends(node_id: str, days: int = 7) -> Dict:
    """
    Compute hourly averages, daily peaks, worst pollutants, and trend direction.
    """
    since = datetime.utcnow() - timedelta(days=days)
    db    = SessionLocal()
    try:
        rows = (db.query(SensorReading)
                  .filter(SensorReading.node_id == node_id,
                          SensorReading.timestamp >= since)
                  .order_by(SensorReading.timestamp)
                  .all())
    finally:
        db.close()

    if not rows:
        return {}

    df = pd.DataFrame([r.to_dict() for r in rows])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"]      = df["timestamp"].dt.hour
    df["date"]      = df["timestamp"].dt.date

    hourly_avg = df.groupby("hour")["aqi"].mean().round(1).to_dict()
    daily_max  = df.groupby("date")["aqi"].max().reset_index()
    daily_max["date"] = daily_max["date"].astype(str)
    daily_series = daily_max.set_index("date")["aqi"].to_dict()

    pollutants = ["pm25", "pm10", "co", "no2", "o3", "co2"]
    means      = {p: round(df[p].mean(), 2) for p in pollutants if p in df.columns}
    worst_poll = max(means, key=means.get) if means else "pm25"

    # AQI trend (simple linear slope)
    if len(df) >= 5:
        x     = np.arange(len(df))
        slope = float(np.polyfit(x, df["aqi"].fillna(0), 1)[0])
        trend = "improving" if slope < -0.5 else "worsening" if slope > 0.5 else "stable"
    else:
        slope, trend = 0.0, "stable"

    return {
        "node_id":         node_id,
        "period_days":     days,
        "avg_aqi":         round(df["aqi"].mean(), 1),
        "max_aqi":         int(df["aqi"].max()),
        "min_aqi":         int(df["aqi"].min()),
        "hourly_avg":      hourly_avg,
        "daily_max":       daily_series,
        "pollutant_means": means,
        "worst_pollutant": worst_poll,
        "trend":           trend,
        "trend_slope":     round(slope, 4),
        "total_readings":  len(df),
    }


def get_recent_predictions(node_id: str, limit: int = 24) -> List[Dict]:
    db = SessionLocal()
    try:
        return [p.to_dict() for p in
                db.query(Prediction)
                  .filter_by(node_id=node_id)
                  .order_by(Prediction.forecast_time)
                  .limit(limit).all()]
    finally:
        db.close()
