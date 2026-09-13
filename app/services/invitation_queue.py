import logging
import queue
import threading
from dataclasses import dataclass
from typing import Optional

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

    def __init__(self, maxsize: int = 1000):
        self._tasks: queue.Queue[InvitationTask] = queue.Queue(maxsize=maxsize)
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="invitation-receive",
            )
            self._thread.start()
        logger.info("[RECEIVE-QUEUE] Background invitation worker started")

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
                result = client.receive_invitation(task.invitation)
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
                logger.exception("[RECEIVE-QUEUE] OOB processing failed")
            finally:
                self._tasks.task_done()


invitation_receive_queue = InvitationReceiveQueue()
