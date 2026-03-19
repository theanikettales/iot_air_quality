"""
alerts/alert_manager.py
Checks readings against thresholds and dispatches email / SMS alerts.
"""

import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional

from loguru import logger

from config import CONFIG, SAFE_THRESHOLDS, AQI_CATEGORIES
from models import SessionLocal, Alert
from utils.aqi_calculator import get_aqi_category, health_recommendation


# Cooldown: don't re-alert same node within N minutes
ALERT_COOLDOWN_MINUTES = 30
_last_alert: Dict[str, datetime] = {}


def _in_cooldown(node_id: str) -> bool:
    last = _last_alert.get(node_id)
    if last and (datetime.utcnow() - last) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
        return True
    return False


# ──────────────────────────────────────────────
#  Core check
# ──────────────────────────────────────────────
def check_and_alert(data: Dict, socketio=None):
    """
    Evaluate a sensor reading dict. If AQI >= threshold, create an Alert
    record and send notifications.
    """
    aqi      = data.get("aqi", 0)
    node_id  = data["node_id"]

    if aqi < CONFIG.AQI_ALERT_THRESHOLD:
        return

    if _in_cooldown(node_id):
        logger.debug(f"[Alert] {node_id} in cooldown – skipping.")
        return

    category, color, _ = get_aqi_category(aqi)
    recommendation      = health_recommendation(aqi)

    # Identify worst pollutant
    sub_aqis   = data.get("sub_aqis", {})
    worst_poll = max(sub_aqis, key=sub_aqis.get) if sub_aqis else "PM2.5"
    worst_val  = data.get(worst_poll, 0)

    message = (
        f"⚠️ AIR QUALITY ALERT – {data.get('name', node_id)}\n"
        f"AQI: {aqi} ({category})\n"
        f"Worst Pollutant: {worst_poll} = {worst_val}\n"
        f"Time: {data.get('timestamp', datetime.utcnow().isoformat())}\n\n"
        f"Health Advisory: {recommendation}"
    )

    # Save to DB
    db = SessionLocal()
    try:
        alert = Alert(
            node_id   = node_id,
            aqi_value = aqi,
            category  = category,
            pollutant = worst_poll,
            value     = worst_val,
            message   = message,
        )
        db.add(alert)

        # Send notifications
        email_ok = _send_email_alert(data, aqi, category, message)
        alert.sent_email = email_ok
        # SMS (optional)
        sms_ok = _send_sms_alert(message)
        alert.sent_sms = sms_ok

        db.commit()
        logger.warning(f"[Alert] Triggered for {node_id}: AQI={aqi} ({category})")
        _last_alert[node_id] = datetime.utcnow()

        # Broadcast via SocketIO
        if socketio:
            socketio.emit("alert", {"node_id": node_id, "aqi": aqi, "category": category,
                                    "message": message, "color": color})
    except Exception as e:
        db.rollback()
        logger.error(f"[Alert] DB error: {e}")
    finally:
        db.close()


# ──────────────────────────────────────────────
#  Email
# ──────────────────────────────────────────────
def _send_email_alert(data: Dict, aqi: int, category: str, message: str) -> bool:
    if not CONFIG.SMTP_USER or not CONFIG.ALERT_EMAILS:
        return False
    try:
        msg              = MIMEMultipart("alternative")
        msg["Subject"]   = f"[AQMS ALERT] AQI {aqi} – {category} – {data.get('name','')}"
        msg["From"]      = CONFIG.SMTP_USER
        msg["To"]        = ", ".join(CONFIG.ALERT_EMAILS)

        html = f"""
        <html><body style="font-family:Arial,sans-serif;padding:20px;">
          <h2 style="color:#CC0000;">⚠️ Air Quality Alert</h2>
          <table>
            <tr><td><b>Node:</b></td><td>{data.get('name','')}</td></tr>
            <tr><td><b>AQI:</b></td><td style="color:#CC0000;font-size:1.5em;">{aqi} ({category})</td></tr>
            <tr><td><b>PM2.5:</b></td><td>{data.get('PM2.5','-')} µg/m³</td></tr>
            <tr><td><b>CO:</b></td><td>{data.get('CO','-')} ppm</td></tr>
            <tr><td><b>Time:</b></td><td>{data.get('timestamp','')}</td></tr>
          </table>
          <p><b>Recommendation:</b> {health_recommendation(aqi)}</p>
        </body></html>"""

        msg.attach(MIMEText(message, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(CONFIG.SMTP_HOST, CONFIG.SMTP_PORT) as server:
            server.starttls()
            server.login(CONFIG.SMTP_USER, CONFIG.SMTP_PASS)
            server.sendmail(CONFIG.SMTP_USER, CONFIG.ALERT_EMAILS, msg.as_string())

        logger.info(f"[Email] Alert sent to {CONFIG.ALERT_EMAILS}")
        return True
    except Exception as e:
        logger.error(f"[Email] Failed: {e}")
        return False


# ──────────────────────────────────────────────
#  SMS via Twilio (optional)
# ──────────────────────────────────────────────
def _send_sms_alert(message: str) -> bool:
    import os
    sid   = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = os.getenv("TWILIO_FROM_NUMBER")
    nums  = os.getenv("ALERT_PHONE_NUMBERS", "").split(",")

    if not (sid and token and from_ and nums[0]):
        return False

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        short = message[:160]
        for num in nums:
            if num.strip():
                client.messages.create(body=short, from_=from_, to=num.strip())
        logger.info(f"[SMS] Sent to {nums}")
        return True
    except Exception as e:
        logger.error(f"[SMS] Failed: {e}")
        return False


# ──────────────────────────────────────────────
#  Retrieve alerts from DB
# ──────────────────────────────────────────────
def get_recent_alerts(limit: int = 50):
    db = SessionLocal()
    try:
        return [a.to_dict() for a in
                db.query(Alert).order_by(Alert.timestamp.desc()).limit(limit).all()]
    finally:
        db.close()
