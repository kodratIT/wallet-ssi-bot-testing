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

def test_send_presentation_uses_full_proof_request_without_refetch():
    mock_session = Mock()
    mock_resp = Mock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = Mock()
    mock_session.post.return_value = mock_resp

    client = AcapyClient(session=mock_session)
    client.send_presentation(
        "pres-123",
        cred_id="cred-123",
        proof={
            "pres_request": {
                "indy": {
                    "requested_attributes": {
                        "name_ref": {"name": "name"},
                        "id_ref": {"name": "id"},
                    }
                }
            }
        },
    )

    _, kwargs = mock_session.post.call_args
    assert set(kwargs["json"]["indy"]["requested_attributes"]) == {"name_ref", "id_ref"}
    mock_session.get.assert_not_called()
    assert kwargs["json"]["auto_remove"] is True


def test_send_presentation_reads_by_format_proof_request():
    mock_session = Mock()
    mock_resp = Mock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = Mock()
    mock_session.post.return_value = mock_resp

    AcapyClient(session=mock_session).send_presentation(
        "pres-123",
        cred_id="cred-123",
        proof={
            "by_format": {
                "pres_request": {
                    "indy": {
                        "requested_attributes": {"actual_ref": {"name": "id"}}
                    }
                }
            }
        },
    )

    _, kwargs = mock_session.post.call_args
    assert set(kwargs["json"]["indy"]["requested_attributes"]) == {"actual_ref"}

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


def test_list_proofs_follows_pagination():
    mock_session = Mock()
    first_page = Mock()
    first_page.json.return_value = {
        "results": [{"pres_ex_id": "proof-1"}, {"pres_ex_id": "proof-2"}]
    }
    first_page.raise_for_status = Mock()
    second_page = Mock()
    second_page.json.return_value = {"results": [{"pres_ex_id": "proof-3"}]}
    second_page.raise_for_status = Mock()
    mock_session.get.side_effect = [first_page, second_page]

    client = AcapyClient(session=mock_session)

    assert [p["pres_ex_id"] for p in client.list_proofs(page_size=2)] == [
        "proof-1",
        "proof-2",
        "proof-3",
    ]
    assert mock_session.get.call_args_list[0].kwargs["params"] == {"limit": 2, "offset": 0}
    assert mock_session.get.call_args_list[1].kwargs["params"] == {"limit": 2, "offset": 2}
