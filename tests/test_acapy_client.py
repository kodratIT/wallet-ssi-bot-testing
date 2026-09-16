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
    result = client.receive_invitation({"@type": "test"})

    assert result == {"connection_id": "conn-123", "oob_id": None, "mode": "connection"}
    mock_session.post.assert_called_once()


def test_receive_invitation_connectionless_no_connection_id():
    """OOB connectionless (requests~attach saja) tidak punya connection_id — normal."""
    mock_session = Mock()
    mock_resp = Mock()
    mock_resp.json.return_value = {"oob_id": "oob-456", "state": "await_response"}
    mock_resp.raise_for_status = Mock()
    mock_session.post.return_value = mock_resp

    client = AcapyClient(session=mock_session)
    result = client.receive_invitation({"@type": "test"})

    assert result == {"connection_id": None, "oob_id": "oob-456", "mode": "connectionless"}


def test_receive_invitation_no_ids_raises():
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
    client.send_presentation("pres-123", cred_id="cred-123")

    # Credential ID eksplisit dipakai untuk semua requested attributes.
    _, kwargs = mock_session.post.call_args
    assert kwargs["json"]["indy"]["requested_attributes"]["attr1_referent"]["cred_id"] is not None
    assert kwargs["json"]["auto_remove"] is True

def test_find_credential_by_schema():
    mock_session = Mock()
    mock_resp = Mock(status_code=200)
    mock_resp.json.return_value = {
        "results": [
            {
                "referent": "cred-educational-id",
                "schema_id": "RRZAA8JHrvT3vAX2wv1VSK:2:EducationalID:1.0",
            }
        ]
    }
    mock_session.get.return_value = mock_resp

    client = AcapyClient(session=mock_session)

    assert client.find_credential_by_schema(
        "RRZAA8JHrvT3vAX2wv1VSK:2:EducationalID:1.0"
    ) == "cred-educational-id"
