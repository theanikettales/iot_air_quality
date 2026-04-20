from flask import Flask, jsonify
from flask_cors import CORS
import serial
import threading
import time
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

app = Flask(__name__)
CORS(app)  # keep CORS enabled for front-end access

# Configurable via environment variables
SERIAL_PORT = os.getenv('SERIAL_PORT', 'COM6')
BAUD = int(os.getenv('BAUD', '9600'))
BIND_HOST = os.getenv('BIND_HOST', '127.0.0.1')

ser = None
latest = {"aqi": 0, "raw": 0, "ts": None}
latest_lock = threading.Lock()
stop_event = threading.Event()

def open_serial():
    """Try to open the serial port and retry on failure."""
    global ser
    while not stop_event.is_set():
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
            logging.info(f"Opened serial port {SERIAL_PORT} at {BAUD}")
            return
        except Exception as e:
            ser = None
            logging.warning(f"Failed to open serial {SERIAL_PORT}: {e}. Retrying in 5s")
            time.sleep(5)

def parse_line(line: str):
    """Parse a serial line into (aqi, raw) or return None on failure."""
    if not line:
        return None
    parts = line.split(',')
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        logging.debug(f"Received non-integer parts: {parts}")
        return None


def read_serial():
    """Background thread: read lines from serial, parse and store latest values."""
    global latest, ser
    # ensure serial is open
    if ser is None:
        open_serial()

    while not stop_event.is_set():
        if ser is None:
            open_serial()
            time.sleep(0.1)
            continue

        try:
            line = ser.readline().decode(errors='ignore').strip()
            parsed = parse_line(line)
            if parsed:
                aqi, raw = parsed
                with latest_lock:
                    latest['aqi'] = aqi
                    latest['raw'] = raw
                    latest['ts'] = time.time()
        except serial.SerialException as e:
            logging.warning(f"Serial error: {e}. Will attempt reconnect.")
            _handle_serial_disconnect()
        except Exception as e:
            logging.exception(f"Unexpected error in read_serial: {e}")
            time.sleep(1)


def _handle_serial_disconnect():
    """Close and null the serial object and wait briefly before retrying."""
    global ser
    try:
        if ser:
            ser.close()
    except Exception:
        pass
    ser = None
    time.sleep(1)


threading.Thread(target=read_serial, daemon=True).start()


@app.route('/data', methods=['GET'])
def data():
    with latest_lock:
        return jsonify(latest)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "serial_connected": ser is not None})


if __name__ == '__main__':
    try:
        logging.info(f"Starting Flask server on {BIND_HOST}:5000")
        app.run(host=BIND_HOST, port=5000)
    except KeyboardInterrupt:
        logging.info('Shutting down')
        stop_event.set()
        try:
            if ser:
                ser.close()
        except Exception:
            pass