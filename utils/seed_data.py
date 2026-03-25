"""
utils/seed_data.py
Seeds the database with 7 days of realistic historical readings for all nodes.
Run: python utils/seed_data.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import math, random
from datetime import datetime, timedelta
from loguru import logger
from models import init_db, SessionLocal, SensorNode, SensorReading
from utils.aqi_calculator import compute_aqi
from sensors.simulator import SENSOR_NODES

DAYS    = 7
STEP_MIN = 30   # reading every 30 minutes


def seed():
    init_db()
    db = SessionLocal()

    # Create nodes
    for n in SENSOR_NODES:
        if not db.query(SensorNode).filter_by(node_id=n["node_id"]).first():
            db.add(SensorNode(
                node_id   = n["node_id"],
                name      = n["name"],
                latitude  = n["lat"],
                longitude = n["lon"],
            ))
    db.commit()
    logger.info("Nodes created/verified.")

    now     = datetime.utcnow()
    total   = 0
    start_t = now - timedelta(days=DAYS)
    current = start_t

    while current <= now:
        h  = current.hour
        # Diurnal factor
        df = 0.6 + 0.4 * abs(math.sin(math.pi * h / 24))
        if 7 <= h <= 9:
            df *= 1.6
        elif 17 <= h <= 19:
            df *= 1.4
        elif h <= 4 or h >= 23:
            df *= 0.5

        event = random.random() < 0.04

        for n in SENSOR_NODES:
            pf = n["pollution_factor"]
            ef = 2.5 if event else 1.0

            pm25 = max(0, round(18 * pf * df * ef * random.gauss(1, .1), 2))
            pm10 = max(0, round(35 * pf * df * ef * random.gauss(1, .08), 2))
            co   = max(0, round(2.5 * pf * df * random.gauss(1, .08), 3))
            no2  = max(0, round(30 * pf * df * ef * random.gauss(1, .12), 2))
            o3   = max(0, round(45 * random.gauss(1, .10), 2))
            co2  = max(300, round(420 * random.gauss(1, .03), 1))
            voc  = max(0, round(.15 * pf * random.gauss(1, .15), 3))
            temp = round(25 + 5 * math.sin(math.pi * h / 12) + random.gauss(0, .5), 1)
            hum  = round(55 + 15 * math.sin(math.pi * (h - 6) / 12) + random.gauss(0, 2), 1)

            aqi, cat, _, _ = compute_aqi({"PM2.5": pm25, "PM10": pm10,
                                           "CO": co, "NO2": no2, "O3": o3, "CO2": co2})

            db.add(SensorReading(
                node_id=n["node_id"], timestamp=current,
                pm25=pm25, pm10=pm10, co=co, no2=no2, o3=o3,
                co2=co2, voc=voc, temperature=temp, humidity=hum,
                aqi=aqi, aqi_category=cat,
            ))
            total += 1

        if total % 500 == 0:
            db.commit()
            logger.info(f"Seeded {total} readings up to {current}")

        current += timedelta(minutes=STEP_MIN)

    db.commit()
    logger.success(f"✅ Seeded {total} readings across {len(SENSOR_NODES)} nodes for {DAYS} days.")
    db.close()


if __name__ == "__main__":
    seed() 
