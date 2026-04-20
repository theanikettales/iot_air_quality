AQIU serial → HTTP server

This small Flask app reads comma-separated `aqi,raw` lines from a serial port and exposes the latest values via HTTP.

Quick start (Windows cmd.exe):

1. Create a virtualenv and activate it:

```cmd
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies:

```cmd
pip install -r requirements.txt
```

3. Configure (optional):
- `SERIAL_PORT` (default `COM6`)
- `BAUD` (default `9600`)
- `BIND_HOST` (default `127.0.0.1`)

You can set them as environment variables before running the server.

4. Run:

```cmd
python sever.py
```

Endpoints:
- `GET /data` — returns the latest JSON payload {"aqi": int, "raw": int, "ts": unix-epoch}
- `GET /health` — returns {"status": "ok", "serial_connected": bool}

Notes:
- The server will retry opening the serial port if it's not available.
- For development you may want to bind to `0.0.0.0` by setting `BIND_HOST=0.0.0.0`.
