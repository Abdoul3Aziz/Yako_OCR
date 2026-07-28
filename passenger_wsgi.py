"""
Point d'entrée cPanel (Passenger / Setup Python App).

Dans cPanel → Setup Python App :
  - Application startup file : passenger_wsgi.py
  - Application entry point  : application

Puis : pip install -r requirements.txt  (dans le venv cPanel)
et redémarrer l'application.
"""

from __future__ import annotations

import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# Réglages utiles en hébergement mutualisé
os.environ.setdefault("OCR_BACKEND", "hybrid")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
# Désactiver le warmup au boot si Passenger timeout (mettre OCR_WARMUP=1 pour forcer)
os.environ.setdefault("OCR_WARMUP", "0")

from a2wsgi import ASGIMiddleware  # noqa: E402
from app.main import app as asgi_app  # noqa: E402

application = ASGIMiddleware(asgi_app)
