import logging

import requests
from flask import Blueprint, jsonify, request

from app.services.walt_client import WaltClient

logger = logging.getLogger(__name__)

bp = Blueprint("walt", __name__)


@bp.route("/simulate/use-presentation-request", methods=["POST"])
def use_presentation_request():
    """
    Sebelumnya: holder.py:1082 - logic Walt + print + hardcode credential di satu fungsi 60 baris.
    Sekarang: validasi di route, bisnis di WaltClient, credential dari config.
    """
    logger.info("🟢 Menerima request POST /simulate/use-presentation-request")
    try:
        data = request.get_json(force=True, silent=False)
        logger.debug(f"📥 Payload: {data}")

        presentation_url = data.get("presentationRequest") if isinstance(data, dict) else None
        if not presentation_url:
            logger.warning("❌ presentationRequest tidak ditemukan")
            return jsonify({"error": "Missing presentationRequest"}), 400

        logger.info(f"🔗 presentationRequest: {presentation_url[:120]}...")

        # Opsional: allow override credentials via request body untuk reusable testing
        selected = data.get("selectedCredentials") if isinstance(data, dict) else None
        disclosures = data.get("disclosures") if isinstance(data, dict) else None

        client = WaltClient()
        result = client.use_presentation_request(
            presentation_request=presentation_url,
            selected_credentials=selected,
            disclosures=disclosures,
        )

        logger.info("✅ usePresentationRequest berhasil")
        return jsonify({"status": "success", "result": result}), 200

    except requests.HTTPError as e:
        # WaltClient sudah raise_for_status, mapping ke 502 agar k6 tahu upstream error
        detail = e.response.text if hasattr(e, "response") and e.response is not None else str(e)
        logger.error(f"❌ Walt.id HTTPError: {detail}")
        return jsonify({"error": "Failed to use presentation request", "detail": detail}), 502
    except requests.RequestException as e:
        detail = e.response.text if hasattr(e, "response") and e.response is not None else str(e)
        logger.error(f"❌ Walt.id RequestException: {e}")
        return jsonify({"error": "Failed to use presentation request", "detail": detail}), 502
    except Exception as e:
        logger.exception(f"❌ Exception: {e}")
        return jsonify({"error": "Exception during process", "detail": str(e)}), 500
