import os
import sys
import traceback

INTERP = "/usr/bin/python3.12"
# INTERP = "/home/laloyale/venv/bin/python"

if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))

if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ.setdefault("OCR_BACKEND", "hybrid")
os.environ.setdefault("OCR_FALLBACK_MIN_MISSING", "2")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
os.environ.setdefault("OCR_WARMUP", "0")

try:
    from a2wsgi import ASGIMiddleware
    from app.main import app as asgi_app

    application = ASGIMiddleware(asgi_app)

except Exception:
    with open("/home/laloyale/passenger_start.log", "a") as f:
        traceback.print_exc(file=f)
    raise