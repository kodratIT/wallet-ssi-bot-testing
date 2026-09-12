from unittest.mock import Mock, MagicMock
import pytest
from app.services.acapy_client import AcapyClient
from app.extensions import create_session


def test_receive_invitation_success():
    mock_session = Mock()
    mock_resp = Mock()
    mock_resp.json.return_value = {"connection_id": "conn-123"}
    mock_resp.raise_for_status = Mock()
    mock_session.post.return_value = mock_resp

    client = AcapyClient(session=mock_session)
    conn_id = client.receive_invitation({"@type": "test"})

    assert conn_id == "conn-123"
    mock_session.post.assert_called_once()


def test_receive_invitation_no_connection_id_raises():
    mock_session = Mock()
    mock_resp = Mock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = Mock()
    mock_session.post.return_value = mock_resp

    client = AcapyClient(session=mock_session)
    with pytest.raises(ValueError):
        client.receive_invitation({})



def test_shared_session_does_not_retry_post_requests():
    assert "POST" not in create_session().get_adapter("https://").max_retries.allowed_methods

def test_send_presentation_uses_config_defaults():
    mock_session = Mock()
    mock_resp = Mock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = Mock()
    mock_session.post.return_value = mock_resp

    client = AcapyClient(session=mock_session)
    client.send_presentation("pres-123")

    # Cek payload punya cred_id dari config (default custom_credential_id_123)
    _, kwargs = mock_session.post.call_args
    assert kwargs["json"]["indy"]["requested_attributes"]["attr1_referent"]["cred_id"] is not None
    assert kwargs["json"]["auto_remove"] is True
