import os

# Load .env untuk run via python (opsional, tidak wajib untuk docker)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class Settings:
    """
    Centralized configuration - single source of truth.
    Semua nilai diambil dari ENV dengan fallback default.
    Validasi dilakukan di sini, bukan tersebar di file lain.
    """

    # ACA-Py
    ACA_PY_URL: str = os.getenv("ACA_PY_URL", "https://cloud-aries-admin.devlab.biz.id")
    ACA_PY_TOKEN: str = os.getenv(
        "ACA_PY_TOKEN",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ3YWxsZXRfaWQiOiIyYWMyMmI1ZC1jMzZkLTRiNTItODExYy05MjEwYjhkNTY1NTEiLCJpYXQiOjE3ODkyMjYyMDd9.mXWbUH2WiBiM7x_9R9LtsZYjuEhZCn4xx-FRDTVZk44",
    )
    ACA_PY_VERIFY_SSL: bool = os.getenv("ACA_PY_VERIFY_SSL", "false").lower() == "true"
    ACA_PY_TIMEOUT: int = int(os.getenv("ACA_PY_TIMEOUT", "10"))

    # Walt.id
    WALT_WALLET_API_BASE: str = os.getenv("WALT_WALLET_API_BASE", "https://wallet-api.devlab.biz.id")
    WALT_ID_TOKEN: str = os.getenv(
        "WALT_ID_TOKEN",
        "Bearer eyJhbGciOiJIUzI1NiJ9.eyJuYmYiOjE3ODg3NjE4MjQsImV4cCI6MTc5MTM1MzgyNCwiaWF0IjoxNzg4NzYxODI0LCJqdGkiOiI5NGRiYjA0Yy00ZDQ3LTRkNWEtOGQwOS1mOWFlNmM0NmI0ODciLCJpc3MiOiJodHRwOi8vZGV2bGFiLmJpei5pZDo3MDAxIiwiYXVkIjoiaHR0cDovL2RldmxhYi5iaXouaWQ6NzAwMSIsInN1YiI6IjgzZWNkYjFmLWU2NmItNGMxNS05MjcyLTdkZWNhNzgwZThkOCJ9.oQVifCQl2quWspq_4T0R_Li9UGIz3jl5gBIZ_XCBHg0",
    )
    # Auto-login untuk refresh token Walt (jaga-jaga jika token di ENV expired)
    WALT_LOGIN_EMAIL: str = os.getenv("WALT_LOGIN_EMAIL", "kodratcoc@gmail.com")
    WALT_LOGIN_PASSWORD: str = os.getenv("WALT_LOGIN_PASSWORD", "password123")
    WALLET_ID: str = os.getenv("WALLET_ID", "6923c4db-2880-4a6f-8f15-dac3d4f0a3a3")
    WALT_TIMEOUT: int = int(os.getenv("WALT_TIMEOUT", "15"))
    # Credential yang dipakai untuk presentasi - update ke ID yang ada di wallet-api.devlab.biz.id
    # Ditemukan via GET /wallet-api/wallet/{walletId}/credentials: Visa eb288... & UniversityDegree c888...
    WALT_SELECTED_CREDENTIALS: list = os.getenv(
        "WALT_SELECTED_CREDENTIALS", "urn:uuid:c888dce0-1a15-4cce-a830-3a223c9c6fac,urn:uuid:eb288794-ef36-406e-82ee-62f376536f3c"
    ).split(",")

    # Auto-present job
    ENABLE_AUTO_PRESENT: bool = os.getenv("ENABLE_AUTO_PRESENT", "false").lower() == "true"
    AUTO_POLL_INTERVAL: int = int(os.getenv("AUTO_POLL_INTERVAL", "5"))
    AUTO_SEND_DELAY: int = int(os.getenv("AUTO_SEND_DELAY", "2"))
    # Untuk Indy - sebelumnya hardcode custom_credential_id_123 di 5 tempat
    INDY_CRED_ID: str = os.getenv("INDY_CRED_ID", "custom_credential_id_123")
    INDY_ATTR_REFERENT: str = os.getenv("INDY_ATTR_REFERENT", "attr1_referent")

    # Flask
    FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5050"))
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    @property
    def aca_py_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.ACA_PY_TOKEN:
            # ACA_PY_TOKEN env sudah tanpa "Bearer " prefix di beberapa deploy,
            # normalisasi agar selalu Bearer
            token = self.ACA_PY_TOKEN
            if not token.startswith("Bearer "):
                token = f"Bearer {token}"
            headers["Authorization"] = token
        return headers

    @property
    def walt_headers(self) -> dict:
        # WALT_ID_TOKEN sudah include "Bearer "
        token = self.WALT_ID_TOKEN
        if not token.startswith("Bearer "):
            token = f"Bearer {token}"
        return {
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def validate(self):
        """Dipanggil saat startup untuk fail-fast jika config kritis hilang."""
        warnings = []
        if not self.ACA_PY_URL:
            warnings.append("ACA_PY_URL kosong")
        if not self.WALT_WALLET_API_BASE:
            warnings.append("WALT_WALLET_API_BASE kosong")
        return warnings


settings = Settings()
