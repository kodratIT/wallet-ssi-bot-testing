"""
Suport `python -m app` tanpa Docker.
"""

from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    app.run(host=settings.FLASK_HOST, port=settings.FLASK_PORT, debug=settings.FLASK_DEBUG, threaded=True)
