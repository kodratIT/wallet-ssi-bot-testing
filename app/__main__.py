"""
Suport `python -m app` tanpa Docker.
"""

from app import create_app
from app.config import settings
from app.jobs.auto_present import auto_present_job

app = create_app()

if __name__ == "__main__":
    import logging

    if settings.ENABLE_AUTO_PRESENT:
        auto_present_job.start()
        logging.info("✅ Auto-present ENABLED")
    app.run(host=settings.FLASK_HOST, port=settings.FLASK_PORT, debug=settings.FLASK_DEBUG, threaded=True)
