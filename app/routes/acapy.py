import logging
import queue
import secrets

import requests
from flask import Blueprint, jsonify, request

from app.config import settings
from app.services.acapy_client import AcapyClient
from app.services.credential_store import credential_store
from app.services.invitation_queue import invitation_receive_queue
from app.utils.invitation import decode_base64_invitation

logger = logging.getLogger(__name__)

bp = Blueprint("acapy", __name__)
# Connection-only mode: present/proof routes hidden when ENABLE_AUTO_PRESENT=false.
# ACA-Py auto_accept=true sudah handle connection; wallet auto-accept/ping/credential/present
# di-handle ACA-Py sendiri. Set ENABLE_AUTO_PRESENT=true untuk aktifkan lagi.


@bp.route("/simulate/acapy/receive", methods=["POST"])
def receive_acapy_invitation():
    """
    Menerima undangan OOB yang dienkode base64url.
    Mendukung cred_id dinamis dari k6: ?cred_id=xxx atau JSON {cred_id} atau header X-Cred-Id
    Jika k6 kirim cred_id saat connected (step 2), credential_store akan dipakai AutoPresentJob.
    """
    logger.info("🛬 [RECEIVE] Permintaan penerimaan undangan diterima")

    # k6 bisa kirim cred_id via query / header / json (opsional, fallback ke ENV)
    cred_id = request.args.get("cred_id") or request.args.get("credId") or request.headers.get("X-Cred-Id")
    referent = request.args.get("referent") or request.headers.get("X-Referent")
    # Jika body JSON (k6 kirim {oob, cred_id}), ekstrak
    json_data = request.get_json(silent=True)
    if isinstance(json_data, dict):
        cred_id = cred_id or json_data.get("cred_id") or json_data.get("credId")
        referent = referent or json_data.get("referent")
        # jika json berisi oob, pakai itu sebagai raw_body, bukan whole json
        if "oob" in json_data:
            raw_body = json_data["oob"]
        elif "invitation" in json_data:
            raw_body = json_data["invitation"]
        else:
            raw_body = request.get_data(as_text=True)
    else:
        raw_body = request.get_data(as_text=True)

    if cred_id:
        credential_store.set_for_connection(None, cred_id, referent)
        logger.info(f"📥 [RECEIVE] cred_id dinamis dari k6: {cred_id} (referent={referent or 'attr1_referent'})")

    logger.info(f"🔍 [RECEIVE] Raw body: {raw_body[:200]}...")

    try:
        invitation = decode_base64_invitation(raw_body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    logger.info("📥 [RECEIVE] Menambahkan undangan ke background queue...")
    try:
        invitation_receive_queue.enqueue(invitation, cred_id, referent, request.headers.get("X-K6-Run-ID"))
    except queue.Full:
        logger.error("❌ [RECEIVE] Queue penerimaan undangan penuh")
        return jsonify({"error": "Queue penerimaan undangan penuh, coba lagi"}), 503

    return jsonify({
        "status": "undangan masuk queue",
        "mode": "pending",
        "connection_id": None,
        "oob_id": None,
    }), 202


@bp.route("/simulate/acapy/cleanup", methods=["POST"])
def cleanup_acapy_connections():
    """Delete only holder and verifier connections created by one K6 stage."""
    expected_token = settings.WALLET_CLEANUP_TOKEN
    supplied_token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not expected_token or not secrets.compare_digest(expected_token, supplied_token):
        return jsonify({"error": "cleanup unauthorized"}), 403

    run_id = request.headers.get("X-K6-Run-ID")
    if not run_id:
        return jsonify({"error": "X-K6-Run-ID is required"}), 400
    if not settings.VERIFIER_ACA_PY_TOKEN:
        return jsonify({"error": "VERIFIER_ACA_PY_TOKEN is not configured"}), 503

    tracked = credential_store.get_run_connections(run_id)
    if not tracked:
        return jsonify({"status": "already clean", "run_id": run_id}), 200

    holder = AcapyClient()
    verifier = AcapyClient(
        base_url=settings.VERIFIER_ACA_PY_URL,
        token=settings.VERIFIER_ACA_PY_TOKEN,
    )
    holder_deleted = verifier_deleted = 0
    failures = []
    for holder_connection_id, invitation_msg_id in tracked.items():
        if holder.delete_connection(holder_connection_id):
            holder_deleted += 1
        else:
            failures.append({"agent": "holder", "connection_id": holder_connection_id})
        if not invitation_msg_id:
            failures.append({"agent": "verifier", "connection_id": holder_connection_id, "error": "invitation ID missing"})
            continue
        try:
            verifier_connections = verifier.list_connections(invitation_msg_id)
        except requests.RequestException:
            failures.append({"agent": "verifier", "invitation_msg_id": invitation_msg_id, "error": "list failed"})
            continue
        for connection in verifier_connections:
            verifier_connection_id = connection.get("connection_id")
            if verifier_connection_id and verifier.delete_connection(verifier_connection_id):
                verifier_deleted += 1
            elif verifier_connection_id:
                failures.append({"agent": "verifier", "connection_id": verifier_connection_id})

    if failures:
        return jsonify({"error": "cleanup incomplete", "run_id": run_id, "failures": failures}), 502
    credential_store.clear_run_connections(run_id)
    return jsonify({
        "status": "cleaned",
        "run_id": run_id,
        "holder_connections_deleted": holder_deleted,
        "verifier_connections_deleted": verifier_deleted,
    }), 200


@bp.route("/simulate/acapy/present", methods=["POST"])
def trigger_auto_present():
    """
    Hidden in connection-only mode. Aktif hanya jika ENABLE_AUTO_PRESENT=true.
    """
    if not settings.ENABLE_AUTO_PRESENT:
        return jsonify({"error": "present disabled (connection-only mode, ENABLE_AUTO_PRESENT=false)"}), 404
    logger.info("🔄 [PRESENT] Permintaan present diterima")
    data = request.get_json(silent=True) or {}
    if not data:
        data = request.form.to_dict() if request.form else {}

    cred_id = data.get("cred_id") or data.get("credId") or request.args.get("cred_id") or request.headers.get("X-Cred-Id")
    referent = data.get("referent") or request.args.get("referent") or data.get("attr_referent")
    conn_id = data.get("connection_id") or data.get("connectionId") or request.args.get("connection_id")
    pres_ex_id = data.get("pres_ex_id") or data.get("presExId") or request.args.get("pres_ex_id")

    if pres_ex_id:
        logger.info(f"🔍 [PRESENT] k6 kirim pres_ex_id={pres_ex_id} cred={cred_id} -> cek record")
        client = AcapyClient()
        try:
            proof = client.get_proof(pres_ex_id)
            logger.info(f"✅ [PRESENT] Proof {pres_ex_id} ditemukan state={proof.get('state')}")
            if proof.get("state") != "request-received":
                return jsonify({"error": f"Proof {pres_ex_id} state bukan request-received: {proof.get('state')}", "detail": proof}), 400
        except requests.RequestException as e:
            try:
                all_proofs = client.list_proofs()
                ids = [p.get("pres_ex_id") for p in all_proofs[:5]]
                detail = str(e.response.text) if hasattr(e, 'response') and e.response is not None else str(e)
                logger.warning(f"⚠️ [PRESENT] pres_ex {pres_ex_id} tidak ditemukan. holder punya: {ids}")
                try:
                    creds = client.list_credentials()
                    cred_ids = [c.get("referent") or c.get("cred_id") or str(c)[:50] for c in creds[:3]]
                except Exception:
                    cred_ids = []
                return jsonify({"error": f"pres_ex_id {pres_ex_id} tidak ditemukan di holder wallet", "detail": detail, "holder_proofs": ids, "available_creds_hint": cred_ids}), 404
            except Exception as ex:
                return jsonify({"error": str(e), "detail": str(ex)}), 500

        if cred_id:
            cred_check = client.get_credential(cred_id)
            if not cred_check:
                pass
            try:
                result = client.send_presentation(pres_ex_id, cred_id=cred_id, referent=referent)
                logger.info(f"✅ [PRESENT] Direct present berhasil untuk {pres_ex_id}")
                return jsonify({"status": "presentation sent", "pres_ex_id": pres_ex_id, "cred_id": cred_id, "result": result}), 200
            except requests.RequestException as e:
                detail = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
                logger.error(f"❌ [PRESENT] Direct present gagal: {detail}")
                return jsonify({"error": "Gagal send presentation", "detail": detail, "pres_ex_id": pres_ex_id, "cred_id": cred_id}), 400
        credential_store.set_for_pres(pres_ex_id, cred_id or "custom_credential_id_123", referent)
        return jsonify({"status": "pres_ex_id disimpan, menunggu auto-present", "pres_ex_id": pres_ex_id}), 200

    if cred_id:
        if conn_id:
            credential_store.set_for_connection(conn_id, cred_id, referent)
        else:
            credential_store.set_for_connection(None, cred_id, referent)
        logger.info(f"✅ [PRESENT] cred_id disimpan: {cred_id} untuk conn={conn_id or 'global'} pres={pres_ex_id or '-'}")
        return jsonify({"status": "cred disimpan, akan dipakai untuk proof berikutnya", "cred_id": cred_id, "connection_id": conn_id, "pres_ex_id": pres_ex_id}), 200

    conn_id_legacy = data.get("connection_id") if isinstance(data, dict) else None
    if conn_id_legacy:
        logger.info(f"🚀 [TRIGGER] Indikasi connection: {conn_id_legacy}")
    else:
        logger.info("🚀 [TRIGGER] Trigger global tanpa connection_id spesifik")
    return jsonify({"status": "background auto-present thread aktif dan akan memproses proof request", "connection_id": conn_id_legacy}), 200


@bp.route("/simulate/acapy/credentials", methods=["GET", "POST", "DELETE"])
def credentials_store():
    """GET/DELETE tetap untuk debug; POST hidden jika connection-only."""
    if request.method == "POST" and not settings.ENABLE_AUTO_PRESENT:
        return jsonify({"error": "present disabled (connection-only mode)"}), 404
    if request.method == "GET":
        if request.args.get("acapy") == "true":
            client = AcapyClient()
            try:
                creds = client.list_credentials()
                return jsonify({"results": creds}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        from app.config import settings as _s

        global_cred, _ = credential_store.get_global()
        return jsonify({"global_cred_id": global_cred, "fallback_env": _s.INDY_CRED_ID}), 200
    if request.method == "DELETE":
        credential_store.clear()
        return jsonify({"status": "cleared"}), 200
    return trigger_auto_present()


@bp.route("/simulate/acapy/proofs", methods=["GET"])
def list_proofs():
    """Hidden in connection-only mode."""
    if not settings.ENABLE_AUTO_PRESENT:
        return jsonify({"error": "present disabled (connection-only mode)"}), 404
    client = AcapyClient()
    try:
        proofs = client.list_proofs()
        filtered = [p for p in proofs if p.get("state") == "request-received"]
        return jsonify({"results": proofs, "request_received": filtered}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
