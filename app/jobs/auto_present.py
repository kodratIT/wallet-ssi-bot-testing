import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import requests

from app.config import settings
from app.services.acapy_client import AcapyClient
from app.services.credential_store import credential_store

logger = logging.getLogger(__name__)


class AutoPresentJob:
    """
    Background job yang memantau proof request dan auto-present.
    Sebelumnya: fungsi global while True di holder.py:868 yang tidak testable.
    Sekarang: class dengan inject AcapyClient, interval & delay dari config, dan stop event.

    Reusable: bisa dipakai tanpa Flask (misal CLI), bisa di-mock client untuk test.
    """

    def __init__(self, client: Optional[AcapyClient] = None):
        self.client = client or AcapyClient()
        self.poll_interval = settings.AUTO_POLL_INTERVAL
        self.send_delay = settings.AUTO_SEND_DELAY
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # protect processed/pending saat Flask threaded + job concurrent
        self._credential_lock = threading.Lock()
        self._connectionless_credential_id: Optional[str] = None
        self._credential_loaded = False
        self._executor = ThreadPoolExecutor(max_workers=settings.AUTO_PRESENT_WORKERS)

        self.processed_ids: set = set()
        self.pending_ids: dict = {}  # pres_ex_id -> timestamp
        self.in_flight_ids: set = set()

    def start(self):
        """Start daemon thread - idempotent."""
        if self._thread and self._thread.is_alive():
            logger.warning("AutoPresentJob sudah berjalan")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, daemon=True, name="auto-present")
        self._thread.start()
        logger.info("✅ Background auto-present thread telah dimulai")
    def stop(self, timeout: float = 5):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def run(self):
        logger.info("👁️ [AUTO] Memulai pemantauan proof request global")
        while not self._stop_event.is_set():
            if self._stop_event.wait(self.poll_interval):
                break

            logger.info("🔁 [AUTO] Polling untuk proof request baru...")
            self._poll_once()

    def _poll_once(self):
        now = time.time()
        with self._lock:
            expired = [
                pid
                for pid, ts in self.pending_ids.items()
                if pid not in self.in_flight_ids and now - ts > self.send_delay + 5
            ]
            for pid in expired:
                self.pending_ids.pop(pid, None)

        try:
            proofs = self.client.list_proofs(state="request-received")
        except requests.RequestException as e:
            logger.error(f"❌ Gagal mengambil proof records: {e}")
            return

        for proof in proofs:
            proof_id = proof.get("pres_ex_id")
            if not proof_id:
                continue

            with self._lock:
                if proof_id in self.processed_ids or proof_id in self.in_flight_ids:
                    continue
                pending_ts = self.pending_ids.get(proof_id)
                if pending_ts is None:
                    self.pending_ids[proof_id] = now
                    if self.send_delay > 0:
                        logger.info(f"🕒 [AUTO] Menunggu {self.send_delay}s untuk proof {proof_id}")
                        continue
                elif now - pending_ts < self.send_delay:
                    continue
                if len(self.in_flight_ids) >= settings.AUTO_PRESENT_WORKERS:
                    break
                self.in_flight_ids.add(proof_id)

            self._executor.submit(self._present_one, proof)

    def _present_one(self, proof: dict) -> None:
        proof_id = proof["pres_ex_id"]
        try:
            # The list endpoint may omit pres_request/by_format. Fetch the
            # complete record before building requested_attributes.
            current = self.client.get_proof(proof_id)
            if current.get("state") != "request-received":
                logger.warning(
                    f"⏭️ Proof {proof_id} sudah bukan request-received "
                    f"({current.get('state')})"
                )
                with self._lock:
                    self.pending_ids.pop(proof_id, None)
                return

            connection_id = current.get("connection_id") or proof.get("connection_id")
            cred_id, referent = credential_store.get_for_proof(proof_id, connection_id)
            if not cred_id:
                if connection_id:
                    with self._lock:
                        pending_since = self.pending_ids.get(proof_id, time.time())
                    waited = time.time() - pending_since
                    if waited < 30:
                        logger.info(
                            f"⏳ [AUTO] Proof {proof_id} menunggu cred_id dari k6 "
                            f"(conn {connection_id[:8]}) waited={int(waited)}s"
                        )
                        return
                    logger.warning(
                        f"⚠️ Timeout menunggu cred dari k6 ({int(waited)}s), "
                        f"fallback ENV untuk {proof_id}: {settings.INDY_CRED_ID}"
                    )
                    cred_id = None if settings.INDY_CRED_ID == "custom_credential_id_123" else settings.INDY_CRED_ID
                    referent = settings.INDY_ATTR_REFERENT
                else:
                    cred_id = self._resolve_connectionless_credential()
                    referent = settings.INDY_ATTR_REFERENT

            logger.info(f"🎯 [AUTO] Proof request {proof_id} akan di-present")
            self.client.send_presentation(
                proof_id,
                cred_id=cred_id,
                referent=referent,
                proof=current,
            )
            logger.info(f"✅ [AUTO] Presentation berhasil untuk {proof_id}")
            with self._lock:
                self.processed_ids.add(proof_id)
                self.pending_ids.pop(proof_id, None)
        except Exception as e:
            logger.error(f"❌ [AUTO] Gagal kirim presentation {proof_id}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Detail: {e.response.status_code} - {e.response.text}")
            with self._lock:
                self.pending_ids.pop(proof_id, None)
        finally:
            with self._lock:
                self.in_flight_ids.discard(proof_id)

    def _resolve_connectionless_credential(self) -> Optional[str]:
        if settings.INDY_CRED_ID != "custom_credential_id_123":
            return settings.INDY_CRED_ID
        with self._credential_lock:
            if not self._credential_loaded:
                self._connectionless_credential_id = self.client.find_credential_by_schema(
                    settings.INDY_SCHEMA_ID
                )
                self._credential_loaded = True
                logger.info(
                    "📌 [AUTO] Credential connectionless resolved once: %s",
                    self._connectionless_credential_id,
                )
            if not self._connectionless_credential_id:
                raise ValueError(
                    f"No ACA-Py credential found for schema {settings.INDY_SCHEMA_ID}"
                )
            return self._connectionless_credential_id


# Singleton untuk app factory jika butuh
auto_present_job = AutoPresentJob()
