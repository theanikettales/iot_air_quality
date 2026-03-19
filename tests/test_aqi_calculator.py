"""
tests/test_aqi_calculator.py
Unit tests for the AQI computation engine.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from utils.aqi_calculator import (
    pollutant_to_aqi, compute_aqi, get_aqi_category,
    health_recommendation
)


class TestPollutantToAQI:

    def test_pm25_good(self):
        assert pollutant_to_aqi("PM2.5", 5.0) <= 50

    def test_pm25_moderate(self):
        v = pollutant_to_aqi("PM2.5", 15.0)
        assert 51 <= v <= 100

    def test_pm25_unhealthy_sg(self):
        v = pollutant_to_aqi("PM2.5", 40.0)
        assert 101 <= v <= 150

    def test_pm25_unhealthy(self):
        v = pollutant_to_aqi("PM2.5", 100.0)
        assert 151 <= v <= 200

    def test_pm25_very_unhealthy(self):
        v = pollutant_to_aqi("PM2.5", 200.0)
        assert 201 <= v <= 300

    def test_pm25_hazardous(self):
        v = pollutant_to_aqi("PM2.5", 300.0)
        assert v >= 301

    def test_pm25_over_cap(self):
        v = pollutant_to_aqi("PM2.5", 999.0)
        assert v == 500

    def test_co_good(self):
        v = pollutant_to_aqi("CO", 2.0)
        assert v <= 50

    def test_no2_moderate(self):
        v = pollutant_to_aqi("NO2", 70.0)
        assert 51 <= v <= 100

    def test_unknown_pollutant(self):
        assert pollutant_to_aqi("UNKNOWN", 100.0) is None

    def test_zero_concentration(self):
        v = pollutant_to_aqi("PM2.5", 0.0)
        assert v == 0


class TestComputeAQI:

    def test_all_good(self):
        readings = {"PM2.5": 5.0, "PM10": 20.0, "CO": 1.0, "NO2": 20.0}
        aqi, label, color, sub = compute_aqi(readings)
        assert aqi <= 50
        assert label == "Good"
        assert color == "#00E400"

    def test_worst_dominates(self):
        readings = {"PM2.5": 200.0, "PM10": 20.0, "CO": 1.0}
        aqi, label, color, sub = compute_aqi(readings)
        assert aqi >= 200

    def test_empty_readings(self):
        aqi, label, color, sub = compute_aqi({})
        assert aqi == 0
        assert label == "Unknown"

    def test_returns_sub_aqis(self):
        readings = {"PM2.5": 15.0, "PM10": 40.0}
        _, _, _, sub = compute_aqi(readings)
        assert "PM2.5" in sub
        assert "PM10" in sub


class TestGetAQICategory:

    @pytest.mark.parametrize("aqi,expected_label", [
        (25,  "Good"),
        (75,  "Moderate"),
        (125, "Unhealthy for SG"),
        (175, "Unhealthy"),
        (250, "Very Unhealthy"),
        (400, "Hazardous"),
    ])
    def test_categories(self, aqi, expected_label):
        label, _, _ = get_aqi_category(aqi)
        assert label == expected_label


class TestHealthRecommendation:

    def test_good_rec(self):
        rec = health_recommendation(30)
        assert "good" in rec.lower() or "enjoy" in rec.lower()

    def test_hazardous_rec(self):
        rec = health_recommendation(400)
        assert "hazardous" in rec.upper() or "indoors" in rec.lower()

    def test_returns_string(self):
        assert isinstance(health_recommendation(0), str)
        assert isinstance(health_recommendation(500), str)


class TestSimulator:

    def test_simulator_produces_valid_reading(self):
        from sensors.simulator import SensorSimulator
        sim = SensorSimulator({
            "node_id": "TEST_001", "name": "Test Node",
            "lat": 28.46, "lon": 77.03, "pollution_factor": 1.0
        })
        reading = sim.read()
        assert "PM2.5" in reading
        assert "aqi" in reading
        assert isinstance(reading["aqi"], int)
        assert 0 <= reading["aqi"] <= 500
        assert 0 <= reading["humidity"] <= 100
        assert -10 <= reading["temperature"] <= 60

    def test_all_five_nodes(self):
        from sensors.simulator import create_simulators
        sims = create_simulators()
        assert len(sims) == 5
        for sim in sims:
            r = sim.read()
            assert r["node_id"].startswith("NODE_")


class TestDatabase:

    def test_init_db(self):
        from models import init_db, SessionLocal, SensorNode
        init_db()
        db = SessionLocal()
        count = db.query(SensorNode).count()
        db.close()
        assert count >= 0   # no error = pass

    def test_create_sensor_node(self):
        from models import init_db, SessionLocal, SensorNode
        init_db()
        db = SessionLocal()
        existing = db.query(SensorNode).filter_by(node_id="TEST_DB_001").first()
        if not existing:
            node = SensorNode(node_id="TEST_DB_001", name="DB Test Node",
                              latitude=28.46, longitude=77.03)
            db.add(node)
            db.commit()
        fetched = db.query(SensorNode).filter_by(node_id="TEST_DB_001").first()
        assert fetched is not None
        assert fetched.name == "DB Test Node"
        db.close()

    def test_create_reading(self):
        from models import init_db, SessionLocal, SensorNode, SensorReading
        from datetime import datetime
        init_db()
        db = SessionLocal()
        node = db.query(SensorNode).filter_by(node_id="TEST_DB_001").first()
        if not node:
            node = SensorNode(node_id="TEST_DB_001", name="DB Test", latitude=28.0, longitude=77.0)
            db.add(node)
            db.commit()
        r = SensorReading(node_id="TEST_DB_001", pm25=12.5, pm10=25.0,
                          co=1.5, no2=20.0, o3=45.0, co2=420.0,
                          temperature=26.0, humidity=60.0, aqi=45, aqi_category="Good")
        db.add(r)
        db.commit()
        fetched = db.query(SensorReading).filter_by(node_id="TEST_DB_001").first()
        assert fetched.pm25 == 12.5
        assert fetched.aqi == 45
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
