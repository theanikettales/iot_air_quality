"""
dashboard/app.py
Flask + SocketIO backend exposing REST API and real-time WebSocket feed.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from loguru import logger

from config import CONFIG
from models import (SessionLocal, SensorNode, SensorReading, Alert,
                    Prediction, init_db)
from utils.aqi_calculator import compute_aqi, get_aqi_category, health_recommendation
from alerts.alert_manager import check_and_alert, get_recent_alerts
from analytics.ml_predictor import train_model, predict_aqi, analyze_trends

# ──────────────────────────────────────────────
#  App setup
# ──────────────────────────────────────────────
app    = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = CONFIG.SECRET_KEY
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

init_db()


# ──────────────────────────────────────────────
#  Real-time broadcast (called by simulator)
# ──────────────────────────────────────────────
def broadcast_reading(data: dict):
    """Push new sensor data to all connected WebSocket clients."""
    socketio.emit("sensor_update", data)
    check_and_alert(data, socketio=socketio)


# ──────────────────────────────────────────────
#  REST API
# ──────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    db = SessionLocal()
    try:
        node_count    = db.query(SensorNode).filter_by(is_active=True).count()
        reading_count = db.query(SensorReading).count()
        return jsonify({"status": "ok", "nodes": node_count, "total_readings": reading_count,
                        "server_time": datetime.utcnow().isoformat()})
    finally:
        db.close()


# ── Nodes ─────────────────────────────────────
@app.route("/api/nodes")
def api_nodes():
    db = SessionLocal()
    try:
        nodes = db.query(SensorNode).all()
        return jsonify([n.to_dict() for n in nodes])
    finally:
        db.close()


@app.route("/api/nodes/<node_id>")
def api_node(node_id):
    db = SessionLocal()
    try:
        node = db.query(SensorNode).filter_by(node_id=node_id).first()
        if not node:
            return jsonify({"error": "Node not found"}), 404
        return jsonify(node.to_dict())
    finally:
        db.close()


# ── Latest readings ────────────────────────────
@app.route("/api/readings/latest")
def api_latest():
    """Latest reading from every active node."""
    db = SessionLocal()
    try:
        nodes   = db.query(SensorNode).filter_by(is_active=True).all()
        results = []
        for node in nodes:
            r = (db.query(SensorReading)
                   .filter_by(node_id=node.node_id)
                   .order_by(SensorReading.timestamp.desc())
                   .first())
            if r:
                d = r.to_dict()
                d["name"]      = node.name
                d["latitude"]  = node.latitude
                d["longitude"] = node.longitude
                d["recommendation"] = health_recommendation(r.aqi or 0)
                results.append(d)
        return jsonify(results)
    finally:
        db.close()


@app.route("/api/readings/latest/<node_id>")
def api_latest_node(node_id):
    db = SessionLocal()
    try:
        r = (db.query(SensorReading)
               .filter_by(node_id=node_id)
               .order_by(SensorReading.timestamp.desc())
               .first())
        if not r:
            return jsonify({"error": "No readings found"}), 404
        d = r.to_dict()
        d["recommendation"] = health_recommendation(r.aqi or 0)
        return jsonify(d)
    finally:
        db.close()


# ── Historical data ────────────────────────────
@app.route("/api/readings/history/<node_id>")
def api_history(node_id):
    hours = int(request.args.get("hours", 24))
    limit = int(request.args.get("limit", 500))
    since = datetime.utcnow() - timedelta(hours=hours)

    db = SessionLocal()
    try:
        rows = (db.query(SensorReading)
                  .filter(SensorReading.node_id == node_id,
                          SensorReading.timestamp >= since)
                  .order_by(SensorReading.timestamp)
                  .limit(limit).all())
        return jsonify([r.to_dict() for r in rows])
    finally:
        db.close()


# ── AQI summary ────────────────────────────────
@app.route("/api/aqi/summary")
def api_aqi_summary():
    """City-wide AQI summary with category breakdown."""
    db = SessionLocal()
    try:
        nodes   = db.query(SensorNode).filter_by(is_active=True).all()
        results = []
        for node in nodes:
            r = (db.query(SensorReading)
                   .filter_by(node_id=node.node_id)
                   .order_by(SensorReading.timestamp.desc()).first())
            if r and r.aqi:
                cat, color, _ = get_aqi_category(r.aqi)
                results.append({
                    "node_id": node.node_id, "name": node.name,
                    "lat": node.latitude, "lon": node.longitude,
                    "aqi": r.aqi, "category": cat, "color": color,
                    "pm25": r.pm25, "pm10": r.pm10, "co": r.co,
                })
        avg_aqi = round(sum(r["aqi"] for r in results) / len(results), 1) if results else 0
        return jsonify({"nodes": results, "city_avg_aqi": avg_aqi,
                        "timestamp": datetime.utcnow().isoformat()})
    finally:
        db.close()


# ── Analytics ──────────────────────────────────
@app.route("/api/analytics/trends/<node_id>")
def api_trends(node_id):
    days = int(request.args.get("days", 7))
    return jsonify(analyze_trends(node_id, days))


@app.route("/api/analytics/predict/<node_id>")
def api_predict(node_id):
    hours = int(request.args.get("hours", 24))
    preds = predict_aqi(node_id, hours)
    return jsonify(preds)


@app.route("/api/analytics/train", methods=["POST"])
def api_train():
    node_id = request.json.get("node_id") if request.json else None
    result  = train_model(node_id)
    return jsonify(result)


# ── Alerts ──────────────────────────────────────
@app.route("/api/alerts")
def api_alerts():
    limit = int(request.args.get("limit", 50))
    return jsonify(get_recent_alerts(limit))


@app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
def api_resolve_alert(alert_id):
    db = SessionLocal()
    try:
        alert = db.query(Alert).filter_by(id=alert_id).first()
        if not alert:
            return jsonify({"error": "Not found"}), 404
        alert.resolved    = True
        alert.resolved_at = datetime.utcnow()
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


# ── Map data ───────────────────────────────────
@app.route("/api/map")
def api_map():
    """Heatmap-ready data: list of {lat, lon, aqi, name}."""
    db = SessionLocal()
    try:
        nodes = db.query(SensorNode).filter_by(is_active=True).all()
        out   = []
        for n in nodes:
            r = (db.query(SensorReading).filter_by(node_id=n.node_id)
                   .order_by(SensorReading.timestamp.desc()).first())
            aqi = r.aqi if r else 0
            _, color, _ = get_aqi_category(aqi)
            out.append({"lat": n.latitude, "lon": n.longitude,
                        "aqi": aqi, "name": n.name,
                        "color": color, "node_id": n.node_id})
        return jsonify(out)
    finally:
        db.close()


# ── SocketIO events ────────────────────────────
@socketio.on("connect")
def on_connect():
    logger.info(f"[WS] Client connected: {request.sid}")
    emit("connected", {"message": "AQMS WebSocket ready"})


@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"[WS] Client disconnected: {request.sid}")


@socketio.on("subscribe_node")
def on_subscribe(data):
    node_id = data.get("node_id")
    logger.info(f"[WS] {request.sid} subscribing to {node_id}")


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────
def start_simulator():
    """Launch sensor simulator in background, feeding data into the API."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from sensors.simulator import create_simulators, MQTTSensorPublisher
    from cloud.mqtt_subscriber import ingest_direct

    sims = create_simulators()
    pub  = MQTTSensorPublisher(sims, interval=CONFIG.READ_INTERVAL)
    pub.start(on_reading=lambda d: ingest_direct(d, on_new_reading=broadcast_reading))
    return pub


if __name__ == "__main__":
    pub = start_simulator()
    logger.info(f"[App] Starting on http://0.0.0.0:{CONFIG.PORT}")
    socketio.run(app, host="0.0.0.0", port=CONFIG.PORT, debug=CONFIG.DEBUG, use_reloader=False)
