# 🌬️ IoT-Enabled Air Quality Monitoring System
**Team 7 · B.Tech CSE 2024–2028 · K.R. Mangalam University**
Mentor: Dr. Yogita Yashveer Raghav | Team ID: 26E2094

---

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Setup & Installation](#setup--installation)
6. [Running the System](#running-the-system)
7. [API Reference](#api-reference)
8. [Module Descriptions](#module-descriptions)
9. [Configuration](#configuration)
10. [Team](#team)

---

## Project Overview

A full-stack IoT system that:
- **Simulates** 5 ESP32-based sensor nodes (MQ-135, MQ-7, PMS5003, DHT22, GPS)
- **Computes** US-EPA AQI from PM2.5, PM10, CO, NO₂, O₃, CO₂, VOC
- **Streams** real-time data via MQTT → Cloud → WebSocket
- **Visualizes** live and historical data on an interactive dashboard
- **Alerts** via email/SMS when AQI exceeds safe thresholds
- **Forecasts** future AQI using a Gradient Boosting ML model

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  SENSING LAYER         GATEWAY         CLOUD        APP     │
│                                                             │
│  [ESP32+Sensors]  ──MQTT──▶  [Broker]  ──▶  [Flask API]   │
│  MQ-135 (NH₃/CO₂)           Mosquitto       REST + WS      │
│  MQ-7   (CO)                                               │
│  PMS5003 (PM2.5)   ──▶  [Subscriber]  ──▶  [SQLite DB]    │
│  DHT22  (Temp/Hum)          saves readings                 │
│  GPS    (Location)                                         │
│                         [ML Model]    ──▶  [Dashboard]     │
│  [Simulator]  ──▶       AQI Forecast       Chart.js        │
│  5 virtual nodes                           SocketIO Live   │
│                         [Alert Mgr]   ──▶  Email / SMS     │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Hardware (simulated) | ESP32, MQ-135, MQ-7, PMS5003, DHT22, GPS |
| Communication | MQTT (paho-mqtt), HTTP REST, WebSocket |
| Backend | Python, Flask, Flask-SocketIO, Flask-CORS |
| Database | SQLite via SQLAlchemy ORM |
| Analytics / ML | Scikit-learn (GradientBoosting), Pandas, NumPy |
| Frontend | HTML5, CSS3, Chart.js 4, Socket.IO client |
| Alerts | SMTP Email, Twilio SMS |
| AQI Standard | US-EPA 2012 Breakpoints |

---

## Project Structure

```
iot_air_quality/
│
├── main.py                    # Entry point (web / simulate / seed / train / test)
├── config.py                  # AQI breakpoints, constants, AppConfig
├── models.py                  # SQLAlchemy ORM: SensorNode, SensorReading, Alert, Prediction
├── requirements.txt
├── .env.example               # Copy to .env and fill in credentials
│
├── sensors/
│   └── simulator.py           # SensorSimulator + MQTTSensorPublisher (5 nodes)
│
├── cloud/
│   └── mqtt_subscriber.py     # MQTT subscriber → DB ingest
│
├── alerts/
│   └── alert_manager.py       # Threshold checking, email/SMS dispatch
│
├── analytics/
│   └── ml_predictor.py        # Feature engineering, model training, AQI forecasting
│
├── utils/
│   ├── aqi_calculator.py      # US-EPA AQI formula, category lookup, health advisories
│   └── seed_data.py           # Seeds 7 days of historical readings
│
├── dashboard/
│   ├── app.py                 # Flask + SocketIO REST API + real-time broadcast
│   └── templates/
│       └── index.html         # Full interactive dashboard (Chart.js + live updates)
│
├── tests/
│   └── test_aqi_calculator.py # pytest unit tests (AQI, simulator, DB)
│
└── data/                      # Auto-created: aqms.db, aqi_model.pkl, aqi_scaler.pkl
```

---

## Setup & Installation

### Prerequisites
- Python 3.9+
- (Optional) Mosquitto MQTT broker for real hardware

### 1. Clone / extract the project
```bash
cd iot_air_quality
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env — set SMTP credentials for email alerts (optional)
```

---

## Running the System

### Option A — Full Web Dashboard (recommended)
```bash
python main.py --mode web
```
Open **http://localhost:5000** in your browser.

The simulator starts automatically, generating readings every 30 seconds from all 5 sensor nodes. The dashboard shows live AQI, pollutant levels, charts, a sensor map, and alerts — all updating in real time.

### Option B — Seed historical data first, then train ML model
```bash
# 1. Generate 7 days of historical data
python main.py --mode seed

# 2. Train the AQI forecasting model
python main.py --mode train

# 3. Start the dashboard (forecasts will now be available)
python main.py --mode web
```

### Option C — Console sensor simulation only
```bash
python main.py --mode simulate
```

### Option D — Run unit tests
```bash
python main.py --mode test
# or directly:
pytest tests/ -v
```

---

## API Reference

All endpoints return JSON.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | System health + counts |
| GET | `/api/nodes` | All sensor nodes |
| GET | `/api/nodes/<node_id>` | Single node info |
| GET | `/api/readings/latest` | Latest reading from every node |
| GET | `/api/readings/latest/<node_id>` | Latest reading for one node |
| GET | `/api/readings/history/<node_id>?hours=24` | Historical readings |
| GET | `/api/aqi/summary` | City-wide AQI summary + heatmap data |
| GET | `/api/analytics/trends/<node_id>?days=7` | Trend analysis |
| GET | `/api/analytics/predict/<node_id>?hours=24` | ML forecast |
| POST | `/api/analytics/train` | Re-train ML model |
| GET | `/api/alerts?limit=50` | Recent alerts |
| POST | `/api/alerts/<id>/resolve` | Mark alert resolved |
| GET | `/api/map` | Heatmap-ready lat/lon/aqi list |

### WebSocket Events
| Event | Direction | Payload |
|---|---|---|
| `sensor_update` | Server → Client | Full reading dict |
| `alert` | Server → Client | Alert dict |
| `subscribe_node` | Client → Server | `{"node_id": "NODE_001"}` |

---

## Module Descriptions

### `config.py`
Central configuration: US-EPA AQI breakpoints for all 6 pollutants, category labels and colors, safe threshold values, and the `AppConfig` dataclass loaded from `.env`.

### `models.py`
Four SQLAlchemy models:
- **SensorNode** — physical node registry (id, location, lat/lon, firmware)
- **SensorReading** — time-series readings with all pollutants + computed AQI
- **Alert** — triggered alerts with notification status
- **Prediction** — ML forecast records

### `sensors/simulator.py`
`SensorSimulator` generates realistic readings with diurnal variation (rush-hour peaks at 8 AM and 6 PM, clean air at 3 AM), random pollution events (industrial bursts, 3% probability per cycle), and Gaussian sensor noise. `MQTTSensorPublisher` runs all 5 nodes in a background thread and publishes to `aqms/sensors/<node_id>/data`.

### `utils/aqi_calculator.py`
Pure-Python implementation of the US-EPA linear interpolation formula. `compute_aqi()` takes a dict of pollutant concentrations, computes the sub-AQI for each using breakpoint tables, and returns the dominant (highest) overall AQI with its category, hex color, and health advisory.

### `analytics/ml_predictor.py`
`train_model()` pulls historical readings from the DB, engineers 20+ features (rolling means, standard deviations, time-of-day sine/cosine encodings, weekend flag), trains a Gradient Boosting Regressor, evaluates on a holdout set, and saves the model + scaler to `data/`. `predict_aqi()` generates per-hour forecasts up to 24 hours ahead.

### `alerts/alert_manager.py`
Checks every incoming reading against `AQI_ALERT_THRESHOLD` (default 150). When triggered: saves an `Alert` record, sends an HTML email via SMTP, optionally sends an SMS via Twilio, emits a WebSocket `alert` event to the dashboard, and enforces a 30-minute cooldown per node to prevent spam.

### `dashboard/app.py`
Flask application with 12 REST endpoints and SocketIO real-time support. Starts the sensor simulator as a daemon thread on launch. `broadcast_reading()` is the callback called by the simulator for every new data point — it persists the reading, checks alerts, and emits a `sensor_update` WebSocket event.

### `dashboard/templates/index.html`
Self-contained dashboard (no build tools required). Features: live AQI gauge with color-coded slider, pollutant concentration tiles with safety-bar indicators, PM2.5/PM10 and AQI trend line charts, hourly pattern bar chart, pollutant radar chart, SVG sensor map, 24-hour forecast strip, alert feed, and all-node comparison table. Automatically falls back to **demo mode** (no backend required) using simulated data generated in-browser.

---

## AQI Color Reference

| Range | Category | Color |
|---|---|---|
| 0–50 | Good | 🟢 #00E400 |
| 51–100 | Moderate | 🟡 #FFFF00 |
| 101–150 | Unhealthy for Sensitive Groups | 🟠 #FF7E00 |
| 151–200 | Unhealthy | 🔴 #FF0000 |
| 201–300 | Very Unhealthy | 🟣 #8F3F97 |
| 301–500 | Hazardous | 🟤 #7E0023 |

---

## Sensor Nodes (Simulated)

| Node ID | Location | Pollution Factor |
|---|---|---|
| NODE_001 | Industrial Zone – North | 1.8× |
| NODE_002 | Residential Area – Central | 1.0× (baseline) |
| NODE_003 | School Vicinity – East | 0.7× (clean) |
| NODE_004 | Highway Corridor – West | 1.5× |
| NODE_005 | Hospital Zone – South | 0.6× (cleanest) |

---

## Team

| Name | Roll | Role |
|---|---|---|
| Bhavishya Tyagi | 2401010168 | Team Leader |
| Divyanshu Deep | 2401010215 | IoT Hardware |
| Aniket Singh | 2501012308 | Backend Dev |
| Tarun Kumar | 2401010124 | Cloud & APIs |
| Sumant Sarkar | 2401010306 | Frontend |
| Hardik Kumar | 2401010199 | Data Analytics |

**Mentor:** Dr. Yogita Yashveer Raghav
**University:** K.R. Mangalam University
**Program:** B.Tech CSE 2024–2028, Semester 3, Section D
