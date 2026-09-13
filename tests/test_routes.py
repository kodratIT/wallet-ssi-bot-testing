import base64
import json
from unittest.mock import patch
from app import create_app
from app.config import settings
from app.services.credential_store import credential_store


def _encode(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def test_health():
    app = create_app(start_background=False)
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/health").json["status"] == "ok"


def test_receive_invalid_body():
    app = create_app(start_background=False)
    client = app.test_client()
    resp = client.post("/simulate/acapy/receive", data="not_base64", content_type="text/plain")
    assert resp.status_code == 400


def test_receive_valid_mocked():
    app = create_app(start_background=False)
    client = app.test_client()
    invitation = {"@type": "test", "label": "x"}
    encoded = _encode(invitation)

    with patch("app.routes.acapy.invitation_receive_queue.enqueue") as enqueue:
        resp = client.post("/simulate/acapy/receive", data=encoded, content_type="text/plain")
        assert resp.status_code == 202
        assert resp.json["mode"] == "pending"
        enqueue.assert_called_once()


def test_receive_connectionless_mocked():
    app = create_app(start_background=False)
    client = app.test_client()
    invitation = {"@type": "test", "label": "x"}
    encoded = _encode(invitation)

    with patch("app.routes.acapy.invitation_receive_queue.enqueue") as enqueue:
        resp = client.post("/simulate/acapy/receive", data=encoded, content_type="text/plain")
        assert resp.status_code == 202
        assert resp.json["mode"] == "pending"
        enqueue.assert_called_once()


def test_cleanup_deletes_tracked_holder_and_verifier_connections(monkeypatch):
    credential_store.clear()
    credential_store.track_connection("run-025", "holder-1", "invite-1")
    monkeypatch.setattr(settings, "WALLET_CLEANUP_TOKEN", "cleanup-secret")
    monkeypatch.setattr(settings, "VERIFIER_ACA_PY_TOKEN", "verifier-secret")

    with patch("app.routes.acapy.AcapyClient") as MockClient:
        holder, verifier = MockClient.return_value, MockClient.return_value
        holder.delete_connection.return_value = True
        verifier.list_connections.return_value = [{"connection_id": "verifier-1"}]
        client = create_app(start_background=False).test_client()
        resp = client.post(
            "/simulate/acapy/cleanup",
            headers={"Authorization": "Bearer cleanup-secret", "X-K6-Run-ID": "run-025"},
        )

    assert resp.status_code == 200
    assert resp.json["holder_connections_deleted"] == 1
    assert resp.json["verifier_connections_deleted"] == 1
    assert credential_store.get_run_connections("run-025") == {}

def test_walt_missing_request(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_AUTO_PRESENT", True)
    app = create_app(start_background=False)
    client = app.test_client()
    resp = client.post("/simulate/use-presentation-request", json={})
    assert resp.status_code == 400


def test_walt_success_mocked(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_AUTO_PRESENT", True)
    app = create_app(start_background=False)
    client = app.test_client()
    with patch("app.routes.walt.WaltClient") as MockClient:
        MockClient.return_value.use_presentation_request.return_value = {"ok": True}
        resp = client.post("/simulate/use-presentation-request", json={"presentationRequest": "openid-vc://test"})
        assert resp.status_code == 200
        assert resp.json["status"] == "success"


def test_walt_disabled_returns_404(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_AUTO_PRESENT", False)
    app = create_app(start_background=False)
    resp = app.test_client().post("/simulate/use-presentation-request", json={})
    assert resp.status_code == 404


def test_sov_presentation_stays_disabled_when_walt_is_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_AUTO_PRESENT", True)
    client = create_app(start_background=False).test_client()

    assert client.post("/simulate/acapy/present", json={}).status_code == 404
    assert client.get("/simulate/acapy/proofs").status_code == 404
