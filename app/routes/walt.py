import logging

import requests
from flask import Blueprint, jsonify, request

from app.config import settings
from app.services.walt_client import WaltClient

logger = logging.getLogger(__name__)

bp = Blueprint("walt", __name__)
# Connection-only mode: hidden when ENABLE_AUTO_PRESENT=false


@bp.route("/simulate/use-presentation-request", methods=["POST"])
def use_presentation_request():
    """
    Hidden in connection-only mode. Aktif hanya jika ENABLE_AUTO_PRESENT=true.
    """
    if not settings.ENABLE_AUTO_PRESENT:
        return jsonify({"error": "present disabled (connection-only mode, ENABLE_AUTO_PRESENT=false)"}), 404
    logger.info("🟢 Menerima request POST /simulate/use-presentation-request")
    try:
        data = request.get_json(force=True, silent=False)
        logger.debug(f"📥 Payload: {data}")

        presentation_url = data.get("presentationRequest") if isinstance(data, dict) else None
        if not presentation_url:
            logger.warning("❌ presentationRequest tidak ditemukan")
            return jsonify({"error": "Missing presentationRequest"}), 400

        logger.info(f"🔗 presentationRequest: {presentation_url[:120]}...")

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
