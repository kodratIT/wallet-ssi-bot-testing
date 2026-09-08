import logging

from flask import Flask

from app.config import settings
from app.routes.acapy import bp as acapy_bp
from app.routes.health import bp as health_bp
from app.routes.walt import bp as walt_bp


def create_app():
    """
    Application factory - pattern Flask yang reusable & testable.
    Sebelumnya: app = Flask(__name__) global di holder.py:18, tidak bisa di-test tanpa import side effect.
    """
    app = Flask(__name__)

    # Logging sekali di factory
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Validate config saat startup
    warnings = settings.validate()
    for w in warnings:
        app.logger.warning(f"Config warning: {w}")

    app.register_blueprint(health_bp)
    app.register_blueprint(acapy_bp)
    app.register_blueprint(walt_bp)

    # Auto-present di Docker (gunicorn app:create_app()) — run.py/ __main__.py sudah handle native,
    # tapi gunicorn bypass itu, jadi start di factory juga bila flag true.
    # ponytail: 2 gunicorn workers = 2 pollers (per-process memory); single worker jika butuh exactly-once
    if settings.ENABLE_AUTO_PRESENT:
        try:
            from app.jobs.auto_present import auto_present_job

            auto_present_job.start()
            app.logger.info("✅ Auto-present ENABLED (factory)")
        except Exception as e:
            app.logger.warning(f"Auto-present gagal start: {e}")

    return app
