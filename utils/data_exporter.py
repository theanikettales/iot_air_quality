"""
utils/data_exporter.py
Export sensor data to CSV / JSON / HTML report.
Usage: python utils/data_exporter.py --format csv --node NODE_001 --days 7
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import json
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger
from models import init_db, SessionLocal, SensorReading, SensorNode


def export_csv(node_id: str, days: int, outfile: str):
    since = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = (db.query(SensorReading)
                  .filter(SensorReading.node_id == node_id,
                          SensorReading.timestamp >= since)
                  .order_by(SensorReading.timestamp).all())
        df = pd.DataFrame([r.to_dict() for r in rows])
        df.to_csv(outfile, index=False)
        logger.success(f"Exported {len(df)} rows → {outfile}")
    finally:
        db.close()


def export_json(node_id: str, days: int, outfile: str):
    since = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = (db.query(SensorReading)
                  .filter(SensorReading.node_id == node_id,
                          SensorReading.timestamp >= since)
                  .order_by(SensorReading.timestamp).all())
        data = [r.to_dict() for r in rows]
        with open(outfile, "w") as f:
            json.dump(data, f, indent=2)
        logger.success(f"Exported {len(data)} records → {outfile}")
    finally:
        db.close()


def export_html_report(node_id: str, days: int, outfile: str):
    """Generate a self-contained HTML report with embedded charts."""
    since = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        node = db.query(SensorNode).filter_by(node_id=node_id).first()
        rows = (db.query(SensorReading)
                  .filter(SensorReading.node_id == node_id,
                          SensorReading.timestamp >= since)
                  .order_by(SensorReading.timestamp).all())
        df = pd.DataFrame([r.to_dict() for r in rows])
    finally:
        db.close()

    if df.empty:
        logger.warning("No data to export.")
        return

    avg_aqi  = round(df["aqi"].mean(), 1)
    max_aqi  = int(df["aqi"].max())
    min_aqi  = int(df["aqi"].min())
    avg_pm25 = round(df["pm25"].mean(), 2) if "pm25" in df else "-"
    node_name = node.name if node else node_id

    timestamps = [str(t)[:16] for t in df["timestamp"]]
    aqis       = df["aqi"].tolist()
    pm25_vals  = df["pm25"].tolist() if "pm25" in df else []

    labels_js = json.dumps(timestamps[::max(1,len(timestamps)//50)])
    aqi_js    = json.dumps(aqis[::max(1,len(aqis)//50)])
    pm25_js   = json.dumps(pm25_vals[::max(1,len(pm25_vals)//50)])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>AQMS Report – {node_name}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  body{{font-family:Segoe UI,sans-serif;background:#0f1117;color:#e8eaf0;margin:0;padding:24px}}
  h1{{color:#00c8ff}} h2{{color:#c8d0e8;border-bottom:1px solid #2a2f45;padding-bottom:8px}}
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0}}
  .stat{{background:#1e2235;border:1px solid #2a2f45;border-radius:12px;padding:16px;text-align:center}}
  .stat-val{{font-size:2rem;font-weight:700;color:#00c8ff}}
  .stat-lbl{{font-size:.8rem;color:#7a8099;margin-top:4px}}
  .chart-box{{background:#1e2235;border:1px solid #2a2f45;border-radius:12px;padding:20px;margin:16px 0}}
  canvas{{max-height:280px}}
  footer{{text-align:center;color:#7a8099;font-size:.75rem;margin-top:40px}}
</style>
</head>
<body>
<h1>🌬️ Air Quality Report</h1>
<p><b>{node_name}</b> · Last {days} days · Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>

<div class="stats">
  <div class="stat"><div class="stat-val">{avg_aqi}</div><div class="stat-lbl">Average AQI</div></div>
  <div class="stat"><div class="stat-val">{max_aqi}</div><div class="stat-lbl">Peak AQI</div></div>
  <div class="stat"><div class="stat-val">{min_aqi}</div><div class="stat-lbl">Best AQI</div></div>
  <div class="stat"><div class="stat-val">{avg_pm25}</div><div class="stat-lbl">Avg PM2.5 µg/m³</div></div>
</div>


<div class="chart-box">
  <h2>AQI Over Time</h2>
  <canvas id="c1"></canvas>
</div>
<div class="chart-box">
  <h2>PM2.5 Concentration (µg/m³)</h2>
  <canvas id="c2"></canvas>
</div>

<footer>IoT Air Quality Monitoring System · Team 7 · K.R. Mangalam University</footer>

<script>
Chart.defaults.color='#7a8099';
new Chart(document.getElementById('c1'),{{type:'line',
  data:{{labels:{labels_js},datasets:[{{label:'AQI',data:{aqi_js},
    borderColor:'#00c8ff',backgroundColor:'rgba(0,200,255,.08)',fill:true,tension:.3,pointRadius:0}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{
    x:{{grid:{{color:'#2a2f45'}}}},y:{{grid:{{color:'#2a2f45'}},min:0}}
  }}}}
}});
new Chart(document.getElementById('c2'),{{type:'line',
  data:{{labels:{labels_js},datasets:[{{label:'PM2.5',data:{pm25_js},
    borderColor:'#ff7e00',backgroundColor:'rgba(255,126,0,.08)',fill:true,tension:.3,pointRadius:0}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{
    x:{{grid:{{color:'#2a2f45'}}}},y:{{grid:{{color:'#2a2f45'}},min:0}}
  }}}}
}});
</script>
</body></html>"""

    with open(outfile, "w") as f:
        f.write(html)
    logger.success(f"HTML report → {outfile}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--format", choices=["csv","json","html"], default="csv")
    p.add_argument("--node",   default="NODE_001")
    p.add_argument("--days",   type=int, default=7)
    p.add_argument("--out",    default=None)
    args = p.parse_args()

    init_db()
    out = args.out or f"aqms_{args.node}_{args.days}d.{args.format}"

    if args.format == "csv":
        export_csv(args.node, args.days, out)
    elif args.format == "json":
        export_json(args.node, args.days, out)
    elif args.format == "html":
        export_html_report(args.node, args.days, out)
