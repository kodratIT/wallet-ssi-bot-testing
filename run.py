#!/usr/bin/env python3
"""
Runner native tanpa Docker.

Usage:
  python run.py              # dev (Flask built-in, reload, log)
  python run.py --prod       # prod (gunicorn 2 workers)
  python run.py --port 5051  # custom port
  ENABLE_AUTO_PRESENT=true python run.py

Alternatif:
  python holder.py           # backward-compat, sama dengan run.py
  python -m app              # via app/__main__.py
"""

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(description="SSI Wallet Bot - run without Docker")
    parser.add_argument("--prod", action="store_true", help="pakai gunicorn (production)")
    parser.add_argument("--host", default=None, help="override FLASK_HOST")
    parser.add_argument("--port", type=int, default=None, help="override FLASK_PORT")
    parser.add_argument("--workers", type=int, default=2, help="gunicorn workers (prod only)")
    args = parser.parse_args()

    # Import setelah parse agar --help cepat
    from app import create_app
    from app.config import settings
    from app.jobs.auto_present import auto_present_job

    host = args.host or settings.FLASK_HOST
    port = args.port or settings.FLASK_PORT

    app = create_app()

    # Validasi ringan
    for w in settings.validate():
        logging.warning(f"Config warning: {w}")

    if settings.ENABLE_AUTO_PRESENT:
        auto_present_job.start()
        logging.info("✅ Auto-present ENABLED")
    else:
        logging.info("⏸️ Auto-present disabled (ENABLE_AUTO_PRESENT=true untuk aktifkan)")

    if args.prod:
        try:
            from gunicorn.app.wsgiapp import WSGIApplication
        except ImportError:
            print("gunicorn belum terinstall: pip install -r requirements.txt", file=sys.stderr)
            sys.exit(1)

        print(f"🚀 Starting PROD (gunicorn) di http://{host}:{port} dengan {args.workers} workers (gthread, threads=4)")
        sys.argv = [
            "gunicorn",
            "-w",
            str(args.workers),
            "-k",
            "gthread",
            "--threads",
            "4",
            "-b",
            f"{host}:{port}",
            "app:create_app()",
        ]
        WSGIApplication().run()
    else:
        print(f"🔧 Starting DEV di http://{host}:{port} (reload={settings.FLASK_DEBUG}, threaded=True)")
        print(f"   Health: http://localhost:{port}/health")
        print(f"   ACA-Py: {settings.ACA_PY_URL}")
        print("   Tekan CTRL+C untuk stop")
        # threaded=True = handle concurrent k6 VUs di dev, prod pakai gunicorn --workers
        app.run(host=host, port=port, debug=settings.FLASK_DEBUG, use_reloader=settings.FLASK_DEBUG, threaded=True)


if __name__ == "__main__":
    main()
