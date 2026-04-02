"""
main.py – IoT Air Quality Monitoring System
Entry point. Run:   python main.py
"""

import sys
import os
import argparse
from loguru import logger

sys.path.insert(0, os.path.dirname(__file__))


def parse_args():
    p = argparse.ArgumentParser(description="IoT AQMS")
    p.add_argument("--mode", choices=["web","simulate","seed","train","test"],
                   default="web",
                   help="web=start dashboard, simulate=print readings, seed=fill DB, train=train ML, test=run tests")
    p.add_argument("--port",  type=int, default=5000)
    p.add_argument("--hours", type=int, default=24, help="Forecast horizon (hours)")
    p.add_argument("--node",  type=str, default=None, help="Node ID to target")
    return p.parse_args()

def main():
    args = parse_args()

    if args.mode == "web":
        logger.info("🌬️  Starting IoT AQMS Dashboard…")
        from models import init_db
        init_db()


        from dashboard.app import app, socketio, start_simulator, CONFIG
        pub = start_simulator()


        logger.info(f"➜  Dashboard:  http://localhost:{args.port}")
        logger.info(f"➜  API status: http://localhost:{args.port}/api/status")


        try:
            socketio.run(app, host="0.0.0.0", port=args.port,
                         debug=False, use_reloader=False)
        except KeyboardInterrupt:
            pub.stop()
            
            logger.info("Shutdown complete.")


    elif args.mode == "simulate":
        logger.info("🔬 Running sensor simulation (Ctrl+C to stop)…")
        from sensors.simulator import create_simulators, MQTTSensorPublisher
        import time
        sims = create_simulators()
        pub  = MQTTSensorPublisher(sims, interval=5)

        def on_reading(d):
            print(f"\n[{d['node_id']}] {d['name']}")
            print(f"  PM2.5={d['PM2.5']} µg/m³  PM10={d['PM10']} µg/m³  CO={d['CO']} ppm")
            print(f"  NO2={d['NO2']} ppb  O3={d['O3']} ppb  CO2={d['CO2']} ppm")
            print(f"  Temp={d['temperature']}°C  Humidity={d['humidity']}%")
            print(f"  ► AQI: {d['aqi']} ({d['aqi_category']})")

        pub.start(on_reading=on_reading)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pub.stop()

    elif args.mode == "seed":
        from utils.seed_data import seed
        seed()

    elif args.mode == "train":
        from models import init_db
        init_db()
        from analytics.ml_predictor import train_model
        result = train_model(args.node)
        if "error" in result:
            logger.error(f"Training failed: {result['error']}")
            logger.info("Tip: Run 'python main.py --mode seed' first to generate historical data.")
        else:
            logger.success(f"Model trained – MAE={result['mae']}  R²={result['r2']}")


    elif args.mode == "test":
        import subprocess
        ret = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=os.path.dirname(__file__)
        )
        sys.exit(ret.returncode)

if __name__ == "__main__":
    main() 
