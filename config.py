"""
config.py – Central configuration for IoT Air Quality Monitoring System
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
#  AQI Breakpoints (US EPA Standard)
# ──────────────────────────────────────────────
AQI_BREAKPOINTS = {
    "PM2.5": [
        (0.0,  12.0,   0,   50),
        (12.1, 35.4,  51,  100),
        (35.5, 55.4, 101,  150),
        (55.5, 150.4,151,  200),
        (150.5,250.4,201,  300),
        (250.5,500.4,301,  500),
    ],
    "PM10": [
        (0,   54,   0,   50),
        (55,  154,  51,  100),
        (155, 254, 101,  150),
        (255, 354, 151,  200),
        (355, 424, 201,  300),
        (425, 604, 301,  500),
    ],
    "CO": [
        (0.0,  4.4,   0,   50),
        (4.5,  9.4,  51,  100),
        (9.5,  12.4,101,  150),
        (12.5, 15.4,151,  200),
        (15.5, 30.4,201,  300),
        (30.5, 50.4,301,  500),
    ],
    "NO2": [
        (0,   53,   0,   50),
        (54,  100,  51,  100),
        (101, 360, 101,  150),
        (361, 649, 151,  200),
        (650, 1249,201,  300),
        (1250,2049,301,  500),
    ],
    "O3": [
        (0,   54,   0,   50),
        (55,  70,  51,  100),
        (71,  85, 101,  150),
        (86,  105,151,  200),
        (106, 200,201,  300),
    ],
    "CO2": [
        (400,  600,  0,   50),
        (601,  800,  51,  100),
        (801,  1000,101,  150),
        (1001, 1500,151,  200),
        (1501, 2000,201,  300),
        (2001, 5000,301,  500),
    ],
}

AQI_CATEGORIES = [
    (0,   50,  "Good",               "#00E400", "Air quality is satisfactory."),
    (51,  100, "Moderate",           "#FFFF00", "Acceptable; sensitive groups may be affected."),
    (101, 150, "Unhealthy for SG",   "#FF7E00", "Sensitive groups face health risks."),
    (151, 200, "Unhealthy",          "#FF0000", "Everyone may experience health effects."),
    (201, 300, "Very Unhealthy",     "#8F3F97", "Health alert – serious effects for everyone."),
    (301, 500, "Hazardous",          "#7E0023", "Emergency conditions; entire population affected."),
]

POLLUTANT_UNITS = {
    "PM2.5":    "µg/m³",
    "PM10":     "µg/m³",
    "CO":       "ppm",
    "NO2":      "ppb",
    "O3":       "ppb",
    "CO2":      "ppm",
    "VOC":      "ppm",
    "temperature": "°C",
    "humidity": "%",
}

SAFE_THRESHOLDS = {
    "PM2.5": 25.0,
    "PM10":  50.0,
    "CO":    9.0,
    "NO2":   40.0,
    "O3":    100.0,
    "CO2":   1000.0,
    "VOC":   0.5,
}


# ──────────────────────────────────────────────
#  App Configuration
# ──────────────────────────────────────────────
@dataclass
class AppConfig:
    # Flask
    SECRET_KEY: str           = os.getenv("SECRET_KEY", "dev_secret")
    DEBUG: bool               = os.getenv("FLASK_DEBUG", "True") == "True"
    PORT: int                 = int(os.getenv("PORT", 5000))

    # MQTT
    MQTT_HOST: str            = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_PORT: int            = int(os.getenv("MQTT_BROKER_PORT", 1883))
    MQTT_USER: str            = os.getenv("MQTT_USERNAME", "")
    MQTT_PASS: str            = os.getenv("MQTT_PASSWORD", "")
    MQTT_TOPIC: str           = os.getenv("MQTT_TOPIC_PREFIX", "aqms/sensors")

    # Database
    DATABASE_URL: str         = os.getenv("DATABASE_URL", "sqlite:///data/aqms.db")

    # Sensor
    READ_INTERVAL: int        = int(os.getenv("SENSOR_READ_INTERVAL", 30))
    RETENTION_DAYS: int       = int(os.getenv("DATA_RETENTION_DAYS", 365))

    # Location
    DEFAULT_LAT: float        = float(os.getenv("DEFAULT_LAT", 28.4595))
    DEFAULT_LON: float        = float(os.getenv("DEFAULT_LON", 77.0266))
    DEFAULT_CITY: str         = os.getenv("DEFAULT_CITY", "Bhiwadi, Rajasthan")

    # AQI Thresholds
    AQI_ALERT_THRESHOLD: int  = int(os.getenv("AQI_UNHEALTHY_SENSITIVE", 150))

    # Email
    SMTP_HOST: str            = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int            = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str            = os.getenv("SMTP_USER", "")
    SMTP_PASS: str            = os.getenv("SMTP_PASSWORD", "")
    ALERT_EMAILS: List[str]   = field(default_factory=lambda: os.getenv("ALERT_RECIPIENTS","").split(","))


CONFIG = AppConfig()
