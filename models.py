"""
models.py – SQLAlchemy ORM models for the AQMS database
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, Float, String,
    DateTime, Boolean, Text, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config import CONFIG

 

Base = declarative_base()


class SensorNode(Base):
    """Represents a physical IoT sensor deployment node."""
    __tablename__ = "sensor_nodes"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    node_id     = Column(String(64), unique=True, nullable=False)
    name        = Column(String(128), nullable=False)
    location    = Column(String(256))
    latitude    = Column(Float, default=CONFIG.DEFAULT_LAT)
    longitude   = Column(Float, default=CONFIG.DEFAULT_LON)
    is_active   = Column(Boolean, default=True)
    firmware    = Column(String(32), default="1.0.0")
    created_at  = Column(DateTime, default=datetime.utcnow)
    last_seen   = Column(DateTime)

    readings    = relationship("SensorReading", back_populates="node", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "node_id": self.node_id,
            "name": self.name,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_active": self.is_active,
            "firmware": self.firmware,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class SensorReading(Base):
    """One time-stamped sensor reading from a node."""
    __tablename__ = "sensor_readings"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    node_id     = Column(String(64), ForeignKey("sensor_nodes.node_id"), nullable=False)
    timestamp   = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Pollutants
    pm25        = Column(Float)   # µg/m³
    pm10        = Column(Float)   # µg/m³
    co          = Column(Float)   # ppm
    no2         = Column(Float)   # ppb
    o3          = Column(Float)   # ppb
    co2         = Column(Float)   # ppm
    voc         = Column(Float)   # ppm

    # Environmental
    temperature = Column(Float)   # °C
    humidity    = Column(Float)   # %

    # Computed
    aqi         = Column(Integer)
    aqi_category= Column(String(32))

    node        = relationship("SensorNode", back_populates="readings")

    __table_args__ = (
        Index("ix_readings_node_ts", "node_id", "timestamp"),
        Index("ix_readings_ts", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "pm25": self.pm25,
            "pm10": self.pm10,
            "co": self.co,
            "no2": self.no2,
            "o3": self.o3,
            "co2": self.co2,
            "voc": self.voc,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "aqi": self.aqi,
            "aqi_category": self.aqi_category,
        }


class Alert(Base):
    """Alert records generated when AQI exceeds thresholds."""
    __tablename__ = "alerts"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    node_id     = Column(String(64), nullable=False)
    timestamp   = Column(DateTime, default=datetime.utcnow)
    aqi_value   = Column(Integer)
    category    = Column(String(32))
    pollutant   = Column(String(16))
    value       = Column(Float)
    message     = Column(Text)
    sent_email  = Column(Boolean, default=False)
    sent_sms    = Column(Boolean, default=False)
    resolved    = Column(Boolean, default=False)
    resolved_at = Column(DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "aqi_value": self.aqi_value,
            "category": self.category,
            "pollutant": self.pollutant,
            "value": self.value,
            "message": self.message,
            "sent_email": self.sent_email,
            "sent_sms": self.sent_sms,
            "resolved": self.resolved,
        }


class Prediction(Base):
    """ML-generated AQI forecast records."""
    __tablename__ = "predictions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    node_id         = Column(String(64), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    forecast_time   = Column(DateTime, nullable=False)
    predicted_aqi   = Column(Integer)
    predicted_pm25  = Column(Float)
    confidence      = Column(Float)
    model_version   = Column(String(16))

    def to_dict(self):
        return {
            "id": self.id,
            "node_id": self.node_id,
            "created_at": self.created_at.isoformat(),
            "forecast_time": self.forecast_time.isoformat(),
            "predicted_aqi": self.predicted_aqi,
            "predicted_pm25": self.predicted_pm25,
            "confidence": self.confidence,
            "model_version": self.model_version,
        }


# ──────────────────────────────────────────────
#  Database setup
# ──────────────────────────────────────────────
import os
os.makedirs("data", exist_ok=True)

engine = create_engine(CONFIG.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables created / verified.")


def get_db():
    """Yield a DB session (for use in Flask routes)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
