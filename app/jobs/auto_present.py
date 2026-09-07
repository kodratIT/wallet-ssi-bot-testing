import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

        # state internal - sebelumnya global set di dalam fungsi
        self.processed_ids: set = set()
        self.pending_ids: dict = {}  # pres_ex_id -> timestamp
        self.first_run = True

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

    def run(self):
        logger.info("👁️ [AUTO] Memulai pemantauan proof request global")
        while not self._stop_event.is_set():
            if self.first_run:
                self._cleanup_all()
                self.first_run = False

            # sleep dengan cek stop event agar bisa di-stop cepat
            if self._stop_event.wait(self.poll_interval):
                break

            logger.info("🔁 [AUTO] Polling untuk proof request baru...")
            self._poll_once()

    def _cleanup_all(self):
        """Hapus semua proof dan connection saat wallet mulai."""
        try:
            logger.info("🧹 [AUTO-FIRST-RUN] Cleanup semua proof records...")
            proofs = self.client.list_proofs()
            proof_ids = [p.get("pres_ex_id") for p in proofs if p.get("pres_ex_id")]
            self._delete_many(
                proof_ids,
                self.client.delete_proof,
                "proof",
            )

            logger.info("🧹 [AUTO-FIRST-RUN] Cleanup semua connections...")
            connections = self.client.list_connections()
            connection_ids = [c.get("connection_id") for c in connections if c.get("connection_id")]
            self._delete_many(
                connection_ids,
                self.client.delete_connection,
                "connection",
            )

            logger.info(
                f"✅ [AUTO-FIRST-RUN] Cleanup selesai: "
                f"{len(proof_ids)} proof, {len(connection_ids)} connection"
            )
        except Exception as e:
            logger.error(f"❌ [AUTO-FIRST-RUN] Gagal cleanup: {e}")

    @staticmethod
    def _delete_many(ids, delete_fn, label):
        if not ids:
            logger.info(f"✅ [AUTO-FIRST-RUN] Tidak ada {label} untuk dihapus")
            return
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(delete_fn, item_id) for item_id in ids]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.warning(f"Gagal hapus {label} saat cleanup: {e}")

    def _poll_once(self):
        now = time.time()
        with self._lock:
            expired = [pid for pid, ts in self.pending_ids.items() if now - ts > self.send_delay + 5]
            for pid in expired:
                self.pending_ids.pop(pid, None)

        try:
            proofs = self.client.list_proofs()
        except requests.RequestException as e:
            logger.error(f"❌ Gagal mengambil proof records: {e}")
            return

        for proof in proofs:
            state = proof.get("state")
            proof_id = proof.get("pres_ex_id")
            if not proof_id:
                continue
            if state != "request-received":
                continue

            with self._lock:
                if proof_id in self.processed_ids:
                    continue
                is_pending = proof_id in self.pending_ids
                pending_ts = self.pending_ids.get(proof_id, 0)

            if is_pending:
                if now - pending_ts < self.send_delay:
                    continue
                try:
                    current = self.client.get_proof(proof_id)
                    if current.get("state") != "request-received":
                        logger.warning(f"⏭️ Proof {proof_id} sudah bukan request-received ({current.get('state')})")
                        with self._lock:
                            self.pending_ids.pop(proof_id, None)
                        continue
                except requests.RequestException as e:
                    logger.warning(f"⚠️ Gagal cek ulang {proof_id}: {e}")
                    with self._lock:
                        self.pending_ids.pop(proof_id, None)
                    continue
            else:
                with self._lock:
                    self.pending_ids[proof_id] = now
                logger.info(f"🕒 [AUTO] Menunggu {self.send_delay}s untuk proof {proof_id}")
                continue

            # Flow Acapy benar: k6 buat connection -> wallet connect -> k6 cek connected -> k6 kirim cred_id -> wallet approve
            # Jadi tunggu cred dinamis dari k6, jika belum ada jangan auto-present dulu (keep pending)
            connection_id = proof.get("connection_id")
            cred_id, referent = credential_store.get_for_proof(proof_id, connection_id)
            if not cred_id:
                # belum ada cred dari k6, cek apakah sudah menunggu lama (>30s) -> fallback ke ENV agar tidak stuck selamanya
                with self._lock:
                    pending_since = self.pending_ids.get(proof_id, now)
                waited = now - pending_since
                if waited < 30:
                    logger.info(f"⏳ [AUTO] Proof {proof_id} menunggu cred_id dari k6 (conn {connection_id[:8] if connection_id else '-'}) waited={int(waited)}s, keep pending")
                    continue
                # timeout fallback
                cred_id, referent = settings.INDY_CRED_ID, settings.INDY_ATTR_REFERENT
                logger.warning(f"⚠️ [AUTO] Timeout menunggu cred dari k6 ({int(waited)}s), fallback ENV untuk {proof_id}: {cred_id}")
            else:
                logger.info(f"📌 [AUTO] Pakai cred dinamis dari k6 untuk {proof_id}: {cred_id} (conn {connection_id[:8] if connection_id else '-'})")

            logger.info(f"🎯 [AUTO] Proof request {proof_id} akan di-present")
            try:
                self.client.send_presentation(proof_id, cred_id=cred_id, referent=referent)
                logger.info(f"✅ [AUTO] Presentation berhasil untuk {proof_id}")
                with self._lock:
                    self.processed_ids.add(proof_id)
                    self.pending_ids.pop(proof_id, None)
            except requests.RequestException as e:
                logger.error(f"❌ [AUTO] Gagal kirim presentation {proof_id}: {e}")
                if hasattr(e, "response") and e.response is not None:
                    logger.error(f"Detail: {e.response.status_code} - {e.response.text}")
                with self._lock:
                    self.pending_ids.pop(proof_id, None)


# Singleton untuk app factory jika butuh
auto_present_job = AutoPresentJob()
