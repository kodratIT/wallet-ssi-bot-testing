import base64
import json
import pytest
from app.utils.invitation import decode_base64_invitation


def _encode_invitation(obj: dict) -> str:
    raw = json.dumps(obj).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def test_decode_plain_base64():
    invitation = {"@type": "https://didcomm.org/out-of-band/1.1/invitation", "label": "Test"}
    encoded = _encode_invitation(invitation)
    result = decode_base64_invitation(encoded)
    assert result == invitation


def test_decode_with_oob_param():
    invitation = {"test": "value"}
    encoded = _encode_invitation(invitation)
    url = f"https://example.com?oob={encoded}&other=param"
    result = decode_base64_invitation(url)
    assert result == invitation


def test_decode_with_padding_needed():
    # tanpa padding, fungsi harus menambah '='
    invitation = {"a": "b"}
    encoded = _encode_invitation(invitation)
    # encoded sudah tanpa padding, decode harus tetap work
    assert decode_base64_invitation(encoded) == invitation


def test_decode_invalid_raises():
    with pytest.raises(ValueError):
        decode_base64_invitation("!!!not_base64!!!")


def test_decode_empty_raises():
    with pytest.raises(ValueError):
        decode_base64_invitation("")
    with pytest.raises(ValueError):
        decode_base64_invitation("   ")
