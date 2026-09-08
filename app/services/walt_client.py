import logging
from typing import Optional

import requests

from app.config import settings
from app.extensions import http_session

logger = logging.getLogger(__name__)


class WaltClient:
    """
    Encapsulasi call ke Walt.id Wallet API (OID4VP).
    Auto-login: setiap request akan coba refresh token via /wallet-api/auth/login
    memakai WALT_LOGIN_EMAIL/PASSWORD agar token selalu fresh (sesuai request user).
    """

    _last_login: float = 0  # ponytail: class-level throttle, one login/5min per worker; per-instance would reset every request

    def __init__(self, session: Optional[requests.Session] = None):
        self.base_url = settings.WALT_WALLET_API_BASE.rstrip("/")
        self.wallet_id = settings.WALLET_ID
        self.headers = settings.walt_headers
        self.timeout = settings.WALT_TIMEOUT
        self.verify = settings.ACA_PY_VERIFY_SSL
        self.session = session or http_session

    def _ensure_fresh_token(self):
        """Login ulang jika token sudah >5 menit atau belum pernah login di proses ini."""
        import time
        now = time.time()
        # Throttle login agar tidak spam setiap request (max 5 menit sekali, atau jika token expired)
        if now - WaltClient._last_login < 300:
            return
        try:
            email = getattr(settings, "WALT_LOGIN_EMAIL", None)
            pwd = getattr(settings, "WALT_LOGIN_PASSWORD", None)
            if not email or not pwd:
                return
            url = f"{self.base_url}/wallet-api/auth/login"
            payload = {"type": "email", "email": email, "password": pwd}
            logger.info(f"🔐 Walt auto-login {email} -> {url}")
            resp = self.session.post(url, json=payload, headers={"Content-Type": "application/json", "accept": "application/json"}, verify=self.verify, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token")
                if token:
                    if not token.startswith("Bearer "):
                        token = f"Bearer {token}"
                    # Update settings dan headers agar request berikutnya pakai token fresh
                    settings.WALT_ID_TOKEN = token
                    self.headers = settings.walt_headers
                    WaltClient._last_login = now
                    logger.info(f"✅ Walt token refreshed exp ~ {token[:30]}...")
                else:
                    logger.warning(f"⚠️ Walt login 200 tapi tanpa token: {data}")
            else:
                logger.warning(f"⚠️ Walt auto-login gagal {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"⚠️ Walt auto-login exception (diabaikan, pakai token lama): {e}")

    def use_presentation_request(
        self,
        presentation_request: str,
        selected_credentials: Optional[list] = None,
        disclosures: Optional[list] = None,
    ) -> dict:
        """
        POST /wallet-api/wallet/{walletId}/exchange/usePresentationRequest
        """
        if not presentation_request:
            raise ValueError("presentationRequest kosong")

        url = f"{self.base_url}/wallet-api/wallet/{self.wallet_id}/exchange/usePresentationRequest"
        payload = {
            "presentationRequest": presentation_request,
            "selectedCredentials": selected_credentials or settings.WALT_SELECTED_CREDENTIALS,
            "disclosures": disclosures,
        }
        logger.info(f"🌍 Walt.id usePresentationRequest -> {url}")
        logger.debug(f"Payload: {payload}")

        # Pastikan token fresh sebelum request (auto-login)
        self._ensure_fresh_token()

        resp = self.session.post(url, json=payload, headers=self.headers, verify=self.verify, timeout=self.timeout)

        # Jika 401, coba refresh token sekali lagi
        if resp.status_code == 401:
            logger.warning("⚠️ Walt 401, coba refresh token dan retry")
            WaltClient._last_login = 0
            self._ensure_fresh_token()
            resp = self.session.post(url, json=payload, headers=self.headers, verify=self.verify, timeout=self.timeout)

        if resp.status_code not in (200, 201):
            logger.error(f"❌ Walt.id gagal: {resp.status_code} - {resp.text}")
            resp.raise_for_status()

        logger.info("✅ Walt.id usePresentationRequest berhasil")
        return resp.json()
