from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.route("/", methods=["GET"])
def home():
    return "✅ SSI Simulation Webhook is Active", 200


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ssi-wallet-bot"}), 200
