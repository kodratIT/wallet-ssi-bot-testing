"""
SSI Wallet Bot - Holder Simulator (Refactored)

Entry point backward-compatible.
- Sebelumnya: 1160 baris monolit di 1 file
- Sekarang: thin wrapper ke app factory (app/__init__.py)

Menjalankan tanpa Docker:
  python holder.py              # dev
  python holder.py --prod       # prod (gunicorn)
  python run.py                 # alternatif dengan arg --port/--host
  python -m app                 # via app/__main__.py

Menjalankan dengan Docker:
  docker-compose up --build
"""

import logging
import sys

from app import create_app
from app.config import settings
from app.jobs.auto_present import auto_present_job

app = create_app()


def _run():
    prod = "--prod" in sys.argv
    if settings.ENABLE_AUTO_PRESENT:
        auto_present_job.start()
        logging.info("✅ Background auto-present thread telah dimulai (ENABLE_AUTO_PRESENT=true)")
    else:
        logging.info("⏸️ Auto-present disabled (set ENABLE_AUTO_PRESENT=true untuk aktifkan)")

    if prod:
        try:
            from gunicorn.app.wsgiapp import WSGIApplication

            sys.argv = ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "-b", f"{settings.FLASK_HOST}:{settings.FLASK_PORT}", "app:create_app()"]
            WSGIApplication().run()
        except ImportError:
            logging.warning("gunicorn belum terinstall, fallback ke Flask dev server")
            app.run(host=settings.FLASK_HOST, port=settings.FLASK_PORT, debug=settings.FLASK_DEBUG, threaded=True)
    else:
        app.run(host=settings.FLASK_HOST, port=settings.FLASK_PORT, debug=settings.FLASK_DEBUG, threaded=True)


if __name__ == "__main__":
    _run()
