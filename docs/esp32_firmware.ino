/*
 * esp32_firmware.ino
 * IoT Air Quality Monitoring System – ESP32 Firmware
 * Team 7 · K.R. Mangalam University
 * Hardware:
 *   - ESP32 Dev Module
 *   - MQ-135 → GPIO34 (ADC1_CH6)
 *   - MQ-7   → GPIO35 (ADC1_CH7)
 *   - PMS5003 → UART2 (RX=16, TX=17)
 *   - DHT22  → GPIO4
 *   - GPS (NEO-6M) → UART1 (RX=12, TX=13)
 *
 * Libraries (install via Arduino Library Manager):
 *   - PubSubClient  (MQTT)
 *   - DHT sensor library (Adafruit)
 *   - TinyGPSPlus
 *   - ArduinoJson
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <TinyGPSPlus.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>

// ─── Config ───────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* MQTT_BROKER   = "192.168.1.100";   // Your broker IP
const int   MQTT_PORT     = 1883;
const char* MQTT_USER     = "aqms_user";
const char* MQTT_PASS     = "aqms_pass";
const char* NODE_ID       = "NODE_001";
const char* NODE_NAME     = "Industrial Zone";

#define PUBLISH_INTERVAL_MS  30000  // 30 seconds

// ─── Pins ──────────────────────────────────────
#define MQ135_PIN   34
#define MQ7_PIN     35
#define DHT_PIN      4
#define DHT_TYPE    DHT22
#define PMS_RX      16
#define PMS_TX      17
#define GPS_RX      12
#define GPS_TX      13

// ─── Objects ──────────────────────────────────
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
DHT          dht(DHT_PIN, DHT_TYPE);
TinyGPSPlus  gps;
HardwareSerial pmsSerial(2);
HardwareSerial gpsSerial(1);

unsigned long lastPublish = 0;

// ─── PMS5003 struct ────────────────────────────
struct PMS5003Data {
  uint16_t pm1_0 = 0, pm2_5 = 0, pm10 = 0;
  bool valid = false;
};

// ─── WiFi ──────────────────────────────────────
void connectWiFi() {
  Serial.print("Connecting WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi connected: " + WiFi.localIP().toString());
}

// ─── MQTT ──────────────────────────────────────
void connectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("MQTT connecting…");
    String clientId = "ESP32-" + String(NODE_ID);
    if (mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)) {
      Serial.println("connected");
      mqtt.subscribe("aqms/cmd/" NODE_ID);  // for OTA commands
    } else {
      Serial.printf("failed rc=%d, retry in 5s\n", mqtt.state());
      delay(5000);
    }
  }
}

// ─── MQ-135 (Air Quality / CO2 / NH3) ─────────
float readMQ135() {
  int raw = analogRead(MQ135_PIN);
  // Simplified: convert ADC to approximate CO2 ppm
  float voltage = raw * (3.3f / 4095.0f);
  float Rs = (3.3f - voltage) / voltage * 10.0f;  // 10kΩ load
  float ratio = Rs / 9.83f;                        // R0 = 9.83 (calibrate in clean air)
  float co2 = 116.6020682f * pow(ratio, -2.769034857f);
  return max(400.0f, min(5000.0f, co2));
}

// ─── MQ-7 (CO) ────────────────────────────────
float readMQ7() {
  int raw = analogRead(MQ7_PIN);
  float voltage = raw * (3.3f / 4095.0f);
  float Rs = (3.3f - voltage) / voltage * 10.0f;
  float ratio = Rs / 27.5f;   // R0 calibration in clean air
  float co_ppm = 99.042f * pow(ratio, -1.518f);
  return max(0.0f, min(1000.0f, co_ppm));
}

// ─── PMS5003 (PM2.5 / PM10) ───────────────────
PMS5003Data readPMS5003() {
  PMS5003Data data;
  if (pmsSerial.available() < 32) return data;

  uint8_t buf[32];
  if (pmsSerial.read() != 0x42) return data;
  if (pmsSerial.read() != 0x4D) return data;
  pmsSerial.readBytes(buf, 30);

  // Checksum
  uint16_t sum = 0x42 + 0x4D;
  for (int i = 0; i < 28; i++) sum += buf[i];
  uint16_t checksum = (buf[28] << 8) | buf[29];
  if (sum != checksum) return data;

  data.pm1_0  = (buf[4]  << 8) | buf[5];
  data.pm2_5  = (buf[6]  << 8) | buf[7];
  data.pm10   = (buf[10] << 8) | buf[11];
  data.valid  = true;
  return data;
}

// ─── DHT22 ────────────────────────────────────
void readDHT(float &temp, float &hum) {
  temp = dht.readTemperature();
  hum  = dht.readHumidity();
  if (isnan(temp)) temp = 25.0f;
  if (isnan(hum))  hum  = 55.0f;
}

// ─── GPS ──────────────────────────────────────
void readGPS(double &lat, double &lon) {
  unsigned long start = millis();
  while (millis() - start < 500) {
    while (gpsSerial.available())
      gps.encode(gpsSerial.read());
  }
  lat = gps.location.isValid() ? gps.location.lat() : 28.4595;
  lon = gps.location.isValid() ? gps.location.lng() : 77.0266;
}

// ─── Setup ─────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pmsSerial.begin(9600,  SERIAL_8N1, PMS_RX, PMS_TX);
  gpsSerial.begin(9600,  SERIAL_8N1, GPS_RX, GPS_TX);
  dht.begin();

  connectWiFi();
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setBufferSize(512);

  Serial.println("IoT AQMS Node ready → " NODE_ID);
}

// ─── Main loop ─────────────────────────────────
void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected())             connectMQTT();
  mqtt.loop();

  if (millis() - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = millis();

    // Read all sensors
    float co2       = readMQ135();
    float co        = readMQ7();
    PMS5003Data pms = readPMS5003();
    float temp, hum;
    readDHT(temp, hum);
    double lat, lon;
    readGPS(lat, lon);

    // Build JSON payload
    StaticJsonDocument<512> doc;
    doc["node_id"]     = NODE_ID;
    doc["name"]        = NODE_NAME;
    doc["timestamp"]   = millis();
    doc["latitude"]    = lat;
    doc["longitude"]   = lon;

    doc["PM2.5"]       = pms.valid ? pms.pm2_5 : 0;
    doc["PM10"]        = pms.valid ? pms.pm10  : 0;
    doc["CO"]          = co;
    doc["CO2"]         = co2;
    doc["temperature"] = temp;
    doc["humidity"]    = hum;

    char payload[512];
    serializeJson(doc, payload);

    String topic = "aqms/sensors/" + String(NODE_ID) + "/data";
    if (mqtt.publish(topic.c_str(), payload)) {
      Serial.println("Published: " + String(payload).substring(0, 80) + "…");
    } else {
      Serial.println("Publish FAILED");
    }
  }
}
