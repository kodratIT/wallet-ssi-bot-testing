import base64
import json
from unittest.mock import patch
from app import create_app


def _encode(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def test_health():
    app = create_app()
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/health").json["status"] == "ok"


def test_receive_invalid_body():
    app = create_app()
    client = app.test_client()
    resp = client.post("/simulate/acapy/receive", data="not_base64", content_type="text/plain")
    assert resp.status_code == 400


def test_receive_valid_mocked():
    app = create_app()
    client = app.test_client()
    invitation = {"@type": "test", "label": "x"}
    encoded = _encode(invitation)

    with patch("app.routes.acapy.AcapyClient") as MockClient:
        MockClient.return_value.receive_invitation.return_value = "conn-xyz"
        resp = client.post("/simulate/acapy/receive", data=encoded, content_type="text/plain")
        assert resp.status_code == 200
        assert resp.json["connection_id"] == "conn-xyz"


def test_walt_missing_request():
    app = create_app()
    client = app.test_client()
    resp = client.post("/simulate/use-presentation-request", json={})
    assert resp.status_code == 400


def test_walt_success_mocked():
    app = create_app()
    client = app.test_client()
    with patch("app.routes.walt.WaltClient") as MockClient:
        MockClient.return_value.use_presentation_request.return_value = {"ok": True}
        resp = client.post("/simulate/use-presentation-request", json={"presentationRequest": "openid-vc://test"})
        assert resp.status_code == 200
        assert resp.json["status"] == "success"
