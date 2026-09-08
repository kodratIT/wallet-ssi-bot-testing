import threading
import time
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class CredentialStore:
    """
    Store dinamis untuk cred_id yang dikirim k6 saat connection connected.
    
    Flow baru:
      1. k6 login -> QR -> POST /simulate/acapy/receive (oob) -> wallet buat connection
      2. k6 polling status -> waiting-connection -> terhubung -> k6 POST /simulate/acapy/present {cred_id} 
      3. AutoPresentJob saat ada proof request, ambil cred_id terbaru untuk connection/proof tsb

    Thread-safe, TTL 5 menit agar tidak leak saat load test.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._lock = threading.Lock()
        # connection_id -> (cred_id, referent, timestamp)
        self._by_connection: Dict[str, Tuple[str, str, float]] = {}
        # pres_ex_id -> (cred_id, referent) - jika k6 tahu pres_ex_id
        self._by_pres: Dict[str, Tuple[str, str]] = {}
        # fallback global - untuk k6 yang tidak kirim connection_id
        self._global: Optional[Tuple[str, str, float]] = None
        self.ttl = ttl_seconds

    def set_for_connection(self, connection_id: Optional[str], cred_id: str, referent: Optional[str] = None):
        referent = referent or "attr1_referent"
        now = time.time()
        with self._lock:
            # Selalu update global sebagai fallback karena wallet connection_id (60e...) != Keycloak connectionId (d41d...)
            # k6 kirim conn d41d..., tapi proof di wallet punya conn 60e..., jadi harus fallback ke global/recent
            self._global = (cred_id, referent, now)
            if connection_id:
                self._by_connection[connection_id] = (cred_id, referent, now)
                logger.info(f"📥 Cred store: conn {connection_id[:8]}... -> {cred_id} ({referent}) + global")
            else:
                logger.info(f"📥 Cred store: global -> {cred_id} ({referent})")

    def set_for_pres(self, pres_ex_id: str, cred_id: str, referent: Optional[str] = None):
        referent = referent or "attr1_referent"
        with self._lock:
            self._by_pres[pres_ex_id] = (cred_id, referent)
            logger.info(f"📥 Cred store: pres {pres_ex_id[:8]}... -> {cred_id}")

    def get_for_proof(self, pres_ex_id: str, connection_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        with self._lock:
            self._cleanup_expired_locked()
            if pres_ex_id in self._by_pres:
                return self._by_pres[pres_ex_id]
            if connection_id and connection_id in self._by_connection:
                cred_id, referent, _ = self._by_connection[connection_id]
                return cred_id, referent
            # fallback: jika k6 kirim untuk conn d41d... tapi proof punya conn 60e... (beda ID per side),
            # pakai cred terbaru yang ada (global atau most recent connection)
            if self._global:
                cred_id, referent, _ = self._global
                return cred_id, referent
            if self._by_connection:
                # ambil yang paling recent
                latest = max(self._by_connection.values(), key=lambda x: x[2])
                return latest[0], latest[1]
            return None, None

    def get_global(self) -> Tuple[Optional[str], Optional[str]]:
        with self._lock:
            self._cleanup_expired_locked()
            if self._global:
                return self._global[0], self._global[1]
            return None, None

    def _cleanup_expired_locked(self):
        now = time.time()
        expired_conns = [k for k, (_, _, ts) in self._by_connection.items() if now - ts > self.ttl]
        for k in expired_conns:
            del self._by_connection[k]
        if self._global and now - self._global[2] > self.ttl:
            self._global = None

    def clear(self):
        with self._lock:
            self._by_connection.clear()
            self._by_pres.clear()
            self._global = None


# singleton
credential_store = CredentialStore()
