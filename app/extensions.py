import logging
import urllib3

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Matikan warning InsecureRequestWarning sekali di sini, bukan di setiap file
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def create_session(
    retries: int = 3,
    backoff_factor: float = 0.3,
    pool_connections: int = 100,
    pool_maxsize: int = 100,
) -> requests.Session:
    """
    Factory untuk requests.Session yang reusable.
    - Retry untuk 502/503/504
    - Timeout harus di-pass per request (biar tidak hang selamanya)
    - Pooling 100 untuk handle burst k6 200 VUs concurrent
    - Thread-safe untuk Flask threaded + gunicorn gthread
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "DELETE"],
    )
    adapter = HTTPAdapter(pool_connections=pool_connections, pool_maxsize=pool_maxsize, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# Global shared session - dipakai oleh services
http_session = create_session()
