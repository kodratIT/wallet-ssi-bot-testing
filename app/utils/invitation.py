import base64
import json
import logging

logger = logging.getLogger(__name__)


def decode_base64_invitation(raw_body: str) -> dict:
    """
    Mendekode body undangan OOB yang dienkode base64url.
    Akan menambahkan padding jika diperlukan.

    Dipindah dari holder.py:47 ke utils agar reusable & testable.
    Raises:
        ValueError: jika decoding gagal
    """
    logger.info("🔍 Mencoba mendekode undangan base64url...")
    if not raw_body or not raw_body.strip():
        raise ValueError("Body undangan kosong")

    # Jika raw_body adalah URL dengan ?oob=..., ambil param oob saja
    # Agar reusable untuk kedua format: plain base64 dan full URL
    if "oob=" in raw_body:
        # ambil value setelah oob= sampai & atau akhir
        raw_body = raw_body.split("oob=")[1].split("&")[0]
        # URL decode jika perlu (k6 sudah decode, tapi jaga-jaga)
        try:
            import urllib.parse

            raw_body = urllib.parse.unquote(raw_body)
        except Exception:
            pass

    raw_body = raw_body.strip()

    try:
        padded = raw_body + "=" * (-len(raw_body) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
        invitation = json.loads(decoded_bytes.decode("utf-8"))
        logger.info("📦 Undangan berhasil didekode")
        logger.debug(json.dumps(invitation, indent=2))
        return invitation
    except Exception as e:
        logger.error(f"❌ Gagal mendekode undangan base64: {e}")
        raise ValueError(f"Gagal mendekode OOB ACA-Py: {e}") from e
