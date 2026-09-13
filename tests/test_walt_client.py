from unittest.mock import Mock

from app.config import settings
from app.services.walt_client import WaltClient


def _response(status, payload):
    response = Mock(status_code=status)
    response.json.return_value = payload
    return response


def test_presentation_reuses_startup_token(monkeypatch):
    monkeypatch.setattr(settings, "WALT_ID_TOKEN", "Bearer startup-token")
    session = Mock()
    session.post.return_value = _response(200, {"ok": True})

    assert WaltClient(session=session).use_presentation_request("openid4vp://test") == {"ok": True}
    assert session.post.call_count == 1
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer startup-token"


def test_presentation_refreshes_only_after_401(monkeypatch):
    monkeypatch.setattr(settings, "WALT_ID_TOKEN", "Bearer expired-token")
    session = Mock()
    session.post.side_effect = [
        _response(401, {}),
        _response(200, {"token": "fresh-token"}),
        _response(200, {"ok": True}),
    ]

    assert WaltClient(session=session).use_presentation_request("openid4vp://test") == {"ok": True}
    assert session.post.call_count == 3
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer fresh-token"
