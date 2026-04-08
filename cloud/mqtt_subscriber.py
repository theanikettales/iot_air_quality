"""
cloud/mqtt_subscriber.py
Subscribes to MQTT topics and persists readings to the database.
Also triggers real-time SocketIO broadcasts and alert checks.
"""

import json
from datetime import datetime
from loguru import logger



from config import CONFIG
from models import SessionLocal, SensorReading, SensorNode, init_db
from utils.aqi_calculator import compute_aqi




class MQTTSubscriber:
    """
    Subscribes to  aqms/sensors/+/data
    Parses payloads, saves to DB, calls optional hooks.
    """

    def __init__(self, on_new_reading=None):
        self.on_new_reading = on_new_reading   # callback(data_dict)
        self._client = None

        try:
            import paho.mqtt.client as mqtt
            self._client = mqtt.Client(client_id="aqms_subscriber")
            self._client.on_connect    = self._on_connect
            self._client.on_message    = self._on_message
            self._client.on_disconnect = self._on_disconnect
            if CONFIG.MQTT_USER:
                self._client.username_pw_set(CONFIG.MQTT_USER, CONFIG.MQTT_PASS)
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("[Subscriber] paho-mqtt not available.")

    def _on_connect(self, client, userdata, flags, rc):
        topic = f"{CONFIG.MQTT_TOPIC}/+/data"
        client.subscribe(topic, qos=1)
        logger.info(f"[Subscriber] Subscribed to {topic}")

    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"[Subscriber] Disconnected (rc={rc})")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            self._save_reading(data)
            if self.on_new_reading:
                self.on_new_reading(data)
        except Exception as e:
            logger.error(f"[Subscriber] Message parse error: {e}")

    def _save_reading(self, data: dict):
        db = SessionLocal()
        try:
            # Ensure node exists
            node = db.query(SensorNode).filter_by(node_id=data["node_id"]).first()
            if not node:
                node = SensorNode(
                    node_id   = data["node_id"],
                    name      = data.get("name", data["node_id"]),
                    latitude  = data.get("latitude", CONFIG.DEFAULT_LAT),
                    longitude = data.get("longitude", CONFIG.DEFAULT_LON),
                )
                db.add(node)

            node.last_seen = datetime.utcnow()

            # Save reading
            reading = SensorReading(
                node_id     = data["node_id"],
                timestamp   = datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                pm25        = data.get("PM2.5"),
                pm10        = data.get("PM10"),
                co          = data.get("CO"),
                no2         = data.get("NO2"),
                o3          = data.get("O3"),
                co2         = data.get("CO2"),
                voc         = data.get("VOC"),
                temperature = data.get("temperature"),
                humidity    = data.get("humidity"),
                aqi         = data.get("aqi"),
                aqi_category = data.get("aqi_category"),
            )
            db.add(reading)
            db.commit()
            logger.debug(f"[DB] Saved reading from {data['node_id']}")
        except Exception as e:
            db.rollback()
            logger.error(f"[DB] Save failed: {e}")
        finally:
            db.close()

    def start(self):
        if not self._available:
            return
        try:
            self._client.connect(CONFIG.MQTT_HOST, CONFIG.MQTT_PORT, keepalive=60)
            self._client.loop_start()
            logger.info("[Subscriber] Running.")
        except Exception as e:
            logger.error(f"[Subscriber] Connect failed: {e}")

    def stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()


def ingest_direct(data: dict, on_new_reading=None):
    """
    Ingest a reading dict directly (without MQTT), used in simulation mode.
    """
    db = SessionLocal()
    try:
        node = db.query(SensorNode).filter_by(node_id=data["node_id"]).first()
        if not node:
            node = SensorNode(
                node_id   = data["node_id"],
                name      = data.get("name", data["node_id"]),
                latitude  = data.get("latitude", CONFIG.DEFAULT_LAT),
                longitude = data.get("longitude", CONFIG.DEFAULT_LON),
            )
            db.add(node)

        node.last_seen = datetime.utcnow()

        reading = SensorReading(
            node_id      = data["node_id"],
            pm25         = data.get("PM2.5"),
            pm10         = data.get("PM10"),
            co           = data.get("CO"),
            no2          = data.get("NO2"),
            o3           = data.get("O3"),
            co2          = data.get("CO2"),
            voc          = data.get("VOC"),
            temperature  = data.get("temperature"),
            humidity     = data.get("humidity"),
            aqi          = data.get("aqi"),
            aqi_category = data.get("aqi_category"),
        )
        db.add(reading)
        db.commit()

        if on_new_reading:
            on_new_reading(data)
    except Exception as e:
        db.rollback()
        logger.error(f"[Ingest] Error: {e}")
    finally:
        db.close()
