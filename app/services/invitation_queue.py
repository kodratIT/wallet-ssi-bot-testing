import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests

from app.config import settings
from app.services.acapy_client import AcapyClient
from app.services.credential_store import credential_store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvitationTask:
    invitation: dict
    cred_id: Optional[str]
    referent: Optional[str]
    run_id: Optional[str]


class InvitationReceiveQueue:
    # ponytail: in-process queue; restart drops pending invitations, use a durable broker if required.

    def __init__(self, maxsize: int = 1000, workers: Optional[int] = None):
        self._tasks: queue.Queue[InvitationTask] = queue.Queue(maxsize=maxsize)
        self._workers = workers or settings.RECEIVE_WORKERS
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            self._threads = [
                threading.Thread(
                    target=self._run,
                    daemon=True,
                    name=f"invitation-receive-{index + 1}",
                )
                for index in range(self._workers)
            ]
            for thread in self._threads:
                thread.start()
        logger.info("[RECEIVE-QUEUE] Started %s background workers", self._workers)

    def enqueue(
        self,
        invitation: dict,
        cred_id: Optional[str],
        referent: Optional[str],
        run_id: Optional[str],
    ) -> None:
        self._tasks.put_nowait(InvitationTask(invitation, cred_id, referent, run_id))

    def _run(self) -> None:
        client = AcapyClient()
        while True:
            task = self._tasks.get()
            try:
                result = self._receive_with_retry(client, task.invitation)
                conn_id = result.get("connection_id")
                oob_id = result.get("oob_id")
                track_id = conn_id or oob_id
                if task.cred_id and track_id:
                    credential_store.set_for_connection(track_id, task.cred_id, task.referent)
                if task.run_id and track_id:
                    credential_store.track_connection(task.run_id, track_id, task.invitation.get("@id"))
                logger.info(
                    "[RECEIVE-QUEUE] OOB processed mode=%s connection_id=%s oob_id=%s",
                    result.get("mode", "connection"),
                    conn_id,
                    oob_id,
                )
            except Exception:
                logger.exception("[RECEIVE-QUEUE] OOB processing failed after retries")
            finally:
                self._tasks.task_done()

    def _receive_with_retry(self, client: AcapyClient, invitation: dict) -> dict:
        """POST receive-invitation dengan retry untuk error jaringan transient.

        ACA-Py cloud melambat (>30s) saat burst 200 paralel sehingga
        requests.ReadTimeout massal. Tanpa retry, task langsung dibuang
        dan flow verifier-nya POLL_TIMEOUT. Backoff eksponensial agar
        tidak menambah beban ke server yang sudah overload.
        """
        max_retries = settings.RECEIVE_MAX_RETRIES
        base_delay = settings.RECEIVE_RETRY_BASE_DELAY
        attempt = 0
        while True:
            try:
                return client.receive_invitation(invitation)
            except requests.RequestException as e:
                attempt += 1
                if attempt > max_retries:
                    raise
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "[RECEIVE-QUEUE] ACA-Py %s, retry %d/%d dalam %.1fs",
                    e.__class__.__name__,
                    attempt,
                    max_retries,
                    delay,
                )
                time.sleep(delay)


invitation_receive_queue = InvitationReceiveQueue()
