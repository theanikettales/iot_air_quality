"""
sensors/simulator.py
Simulates multiple IoT sensor nodes (ESP32 + MQ-135/7, PMS5003, DHT22, GPS).
Publishes realistic time-varying readings via MQTT or directly to the DB.
"""
import json
import math
import random
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

from config import CONFIG, SAFE_THRESHOLDS
from utils.aqi_calculator import compute_aqi


# ──────────────────────────────────────────────
#  Simulated sensor nodes
# ──────────────────────────────────────────────
SENSOR_NODES = [
    {"node_id": "NODE_001", "name": "Industrial Zone – North",    "lat": 28.4710, "lon": 77.0315, "pollution_factor": 1.8},
    {"node_id": "NODE_002", "name": "Residential Area – Central", "lat": 28.4595, "lon": 77.0266, "pollution_factor": 1.0},
    {"node_id": "NODE_003", "name": "School Vicinity – East",     "lat": 28.4523, "lon": 77.0380, "pollution_factor": 0.7},
    {"node_id": "NODE_004", "name": "Highway Corridor – West",    "lat": 28.4680, "lon": 77.0150, "pollution_factor": 1.5},
    {"node_id": "NODE_005", "name": "Hospital Zone – South",      "lat": 28.4450, "lon": 77.0270, "pollution_factor": 0.6},
]
class SensorSimulator:
    """
    Simulates realistic air quality readings with:
    - Diurnal (day/night) variation
    - Random pollution events (trucks, industrial bursts)
    - Sensor noise
    - Gradual drift
    """

    BASE_VALUES = {
        "PM2.5":     18.0,
        "PM10":      35.0,
        "CO":         2.5,
        "NO2":        30.0,
        "O3":         45.0,
        "CO2":       420.0,
        "VOC":         0.15,
        "temperature": 25.0,
        "humidity":   55.0,
    }

    NOISE_FACTORS = {
        "PM2.5": 0.12,   "PM10":  0.10,
        "CO":    0.08,   "NO2":   0.15,
        "O3":    0.10,   "CO2":   0.03,
        "VOC":   0.20,   "temperature": 0.01,   "humidity": 0.02,
    }

    def __init__(self, node_info: Dict):
        self.node_id         = node_info["node_id"]
        self.name            = node_info["name"]
        self.lat             = node_info["lat"]
        self.lon             = node_info["lon"]
        self.pollution_factor = node_info.get("pollution_factor", 1.0)
        self._drift          = {k: 0.0 for k in self.BASE_VALUES}
        self._event_active   = False
        self._event_end      = 0.0

    def _diurnal_factor(self, hour: int) -> float:
        """Rush-hour peaks at ~8 AM and ~6 PM; clean air at 3–4 AM."""
        base = 0.6 + 0.4 * abs(math.sin(math.pi * hour / 24))
        peak = 1.0
        if 7 <= hour <= 9:
            peak = 1.6
        elif 17 <= hour <= 19:
            peak = 1.4
        elif 23 <= hour or hour <= 4:
            peak = 0.5
        return base * peak

    def _check_pollution_event(self):
        """Randomly trigger short pollution spikes (industrial/traffic)."""
        now = time.time()
        if now > self._event_end:
            self._event_active = False
        if not self._event_active and random.random() < 0.03:  # 3% chance per reading
            self._event_active = True
            self._event_end = now + random.randint(120, 600)   # 2–10 minute event
            logger.warning(f"[{self.node_id}] Pollution event triggered for {int(self._event_end - now)}s")

    def read(self) -> Dict:
        """Generate one complete sensor reading."""
        hour = datetime.now().hour
        diurnal = self._diurnal_factor(hour)
        self._check_pollution_event()
        event_boost = 2.5 if self._event_active else 1.0

        readings = {}
        for param, base in self.BASE_VALUES.items():
            noise   = random.gauss(0, self.NOISE_FACTORS[param])
            drift   = self._drift[param]
            factor  = self.pollution_factor * diurnal * event_boost if param not in ("temperature", "humidity") else 1.0
            value   = base * factor * (1 + noise) + drift

            # Clamp to realistic ranges
            clamps = {
                "PM2.5": (0, 500), "PM10": (0, 600), "CO": (0, 50),
                "NO2": (0, 2000), "O3": (0, 500), "CO2": (300, 5000),
                "VOC": (0, 10), "temperature": (-10, 60), "humidity": (5, 100),
            }
            lo, hi = clamps.get(param, (0, 9999))
            readings[param] = round(max(lo, min(hi, value)), 2)

            # Slow drift
            self._drift[param] += random.gauss(0, 0.001)

        # Compute AQI
        pollutant_map = {k: v for k, v in readings.items()
                         if k in ("PM2.5", "PM10", "CO", "NO2", "O3", "CO2")}
        aqi, category, color, sub_aqis = compute_aqi(pollutant_map)

        return {
            "node_id":     self.node_id,
            "name":        self.name,
            "latitude":    self.lat,
            "longitude":   self.lon,
            "timestamp":   datetime.utcnow().isoformat(),
            **readings,
            "aqi":         aqi,
            "aqi_category": category,
            "aqi_color":   color,
            "sub_aqis":    sub_aqis,
        }


# ──────────────────────────────────────────────
#  MQTT Publisher
# ──────────────────────────────────────────────
class MQTTSensorPublisher:
    """
    Publishes simulated readings to an MQTT broker.
    Topic pattern: aqms/sensors/<node_id>/data
    """

    def __init__(self, simulators: List[SensorSimulator], interval: int = CONFIG.READ_INTERVAL):
        self.simulators = simulators
        self.interval   = interval
        self._running   = False
        self._thread: Optional[threading.Thread] = None

        try:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client(client_id="aqms_simulator")
            self.client.on_connect    = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            if CONFIG.MQTT_USER:
                self.client.username_pw_set(CONFIG.MQTT_USER, CONFIG.MQTT_PASS)
            self._mqtt_available = True
        except ImportError:
            self._mqtt_available = False
            logger.warning("paho-mqtt not installed; MQTT publishing disabled.")

    def _on_connect(self, client, userdata, flags, rc):
        logger.info(f"[MQTT] Connected to broker (rc={rc})")

    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"[MQTT] Disconnected (rc={rc})")

    def connect(self):
        if not self._mqtt_available:
            return
        try:
            self.client.connect(CONFIG.MQTT_HOST, CONFIG.MQTT_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"[MQTT] Connection failed: {e}")
            self._mqtt_available = False

    def publish(self, data: Dict):
        if not self._mqtt_available:
            return
        topic = f"{CONFIG.MQTT_TOPIC}/{data['node_id']}/data"
        payload = json.dumps(data)
        self.client.publish(topic, payload, qos=1)
        logger.debug(f"[MQTT] Published → {topic}")

    def start(self, on_reading=None):
        """
        Start continuous publishing in a background thread.
        on_reading(data) is called for each reading (e.g. to save to DB).
        """
        self.connect()
        self._running = True

        def _loop():
            while self._running:
                for sim in self.simulators:
                    data = sim.read()
                    self.publish(data)
                    if on_reading:
                        on_reading(data)
                    logger.info(f"[{data['node_id']}] AQI={data['aqi']} ({data['aqi_category']})")
                time.sleep(self.interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        logger.info(f"[Simulator] Started – publishing every {self.interval}s")

    def stop(self):
        self._running = False
        if self._mqtt_available:
            self.client.loop_stop()
            self.client.disconnect()
        logger.info("[Simulator] Stopped.")


# ──────────────────────────────────────────────
#  Convenience factory
# ──────────────────────────────────────────────
def create_simulators() -> List[SensorSimulator]:
    return [SensorSimulator(n) for n in SENSOR_NODES]


def get_node_info() -> List[Dict]:
    return SENSOR_NODES


if __name__ == "__main__":
    sims = create_simulators()
    pub = MQTTSensorPublisher(sims, interval=5)

    def print_reading(data):
        print(f"\n[{data['node_id']}] {data['name']}")
        print(f"  PM2.5={data['PM2.5']} µg/m³  PM10={data['PM10']} µg/m³")
        print(f"  CO={data['CO']} ppm  NO2={data['NO2']} ppb  O3={data['O3']} ppb")
        print(f"  Temp={data['temperature']}°C  Humidity={data['humidity']}%")
        print(f"  → AQI: {data['aqi']} ({data['aqi_category']})")

    pub.start(on_reading=print_reading)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pub.stop()
