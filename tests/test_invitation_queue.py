import threading
from unittest.mock import Mock, patch

from app.services.invitation_queue import InvitationReceiveQueue


def test_worker_processes_connectionless_invitation():
    client = Mock()
    processed = threading.Event()
    client.receive_invitation.return_value = {
        "connection_id": None,
        "oob_id": "oob-123",
        "mode": "connectionless",
    }
    store = Mock()
    store.track_connection.side_effect = lambda *args: processed.set()
    receive_queue = InvitationReceiveQueue(maxsize=1)

    with patch("app.services.invitation_queue.AcapyClient", return_value=client), patch(
        "app.services.invitation_queue.credential_store", store
    ):
        receive_queue.start()
        receive_queue.enqueue({"@id": "invite-123"}, "cred-123", "attr1_referent", "run-123")
        assert processed.wait(2)

    client.receive_invitation.assert_called_once_with({"@id": "invite-123"})
    store.set_for_connection.assert_called_once_with("oob-123", "cred-123", "attr1_referent")
    store.track_connection.assert_called_once_with("run-123", "oob-123", "invite-123")
