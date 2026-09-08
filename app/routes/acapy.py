import logging

import requests
from flask import Blueprint, jsonify, request

from app.services.acapy_client import AcapyClient
from app.services.credential_store import credential_store
from app.utils.invitation import decode_base64_invitation

logger = logging.getLogger(__name__)

bp = Blueprint("acapy", __name__)
# Lazy client - dibuat per request agar selalu pakai config terbaru
# Bisa juga di-inject via app.extensions


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
        # simpan sebagai global fallback (untuk next proof) - akan di-overwrite jika k6 kirim per connection
        credential_store.set_for_connection(None, cred_id, referent)
        logger.info(f"📥 [RECEIVE] cred_id dinamis dari k6: {cred_id} (referent={referent or 'attr1_referent'})")

    logger.info(f"🔍 [RECEIVE] Raw body: {raw_body[:200]}...")

    try:
        invitation = decode_base64_invitation(raw_body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    logger.info("📨 [RECEIVE] Mengirim undangan ke ACA-Py...")
    try:
        client = AcapyClient()
        conn_id = client.receive_invitation(invitation)
        # jika k6 sudah kirim cred_id di step receive, ikat ke connection_id spesifik
        if cred_id and conn_id:
            credential_store.set_for_connection(conn_id, cred_id, referent)
    except requests.RequestException as e:
        logger.error(f"❌ [RECEIVE] Gagal menerima undangan: {e}")
        detail = str(e)
        if hasattr(e, "response") and e.response is not None:
            detail = e.response.text
        return jsonify({"error": "Gagal menerima undangan oleh ACA-Py", "detail": detail}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 500

    logger.info(f"✅ [RECEIVE] Connection ID: {conn_id}")
    return jsonify({"status": "undangan diterima dan proses auto-present akan dimulai oleh background thread", "connection_id": conn_id}), 200


@bp.route("/simulate/acapy/present", methods=["POST"])
def trigger_auto_present():
    """
    Endpoint untuk k6 kirim cred_id/pres_ex_id saat connection sudah connected (flow Acapy benar).
    - Jika pres_ex_id dikirim: cek record ada di holder wallet, langsung kirim presentation (sinkron)
    - Jika hanya cred_id+connection_id: simpan ke store untuk AutoPresentJob
    - Jika tidak ada cred: legacy trigger
    """
    logger.info("🔄 [PRESENT] Permintaan present diterima")
    data = request.get_json(silent=True) or {}
    if not data:
        data = request.form.to_dict() if request.form else {}

    cred_id = data.get("cred_id") or data.get("credId") or request.args.get("cred_id") or request.headers.get("X-Cred-Id")
    referent = data.get("referent") or request.args.get("referent") or data.get("attr_referent")
    conn_id = data.get("connection_id") or data.get("connectionId") or request.args.get("connection_id")
    pres_ex_id = data.get("pres_ex_id") or data.get("presExId") or request.args.get("pres_ex_id")

    # Jika k6 kirim pres_ex_id -> cek record ada, langsung present (flow pres_ex)
    if pres_ex_id:
        logger.info(f"🔍 [PRESENT] k6 kirim pres_ex_id={pres_ex_id} cred={cred_id} -> cek record")
        client = AcapyClient()
        # cek apakah pres_ex_id ada di holder wallet
        try:
            proof = client.get_proof(pres_ex_id)
            logger.info(f"✅ [PRESENT] Proof {pres_ex_id} ditemukan state={proof.get('state')}")
            if proof.get("state") != "request-received":
                return jsonify({"error": f"Proof {pres_ex_id} state bukan request-received: {proof.get('state')}", "detail": proof}), 400
        except requests.RequestException as e:
            # coba list semua untuk debug
            try:
                all_proofs = client.list_proofs()
                ids = [p.get("pres_ex_id") for p in all_proofs[:5]]
                detail = str(e.response.text) if hasattr(e, 'response') and e.response is not None else str(e)
                logger.warning(f"⚠️ [PRESENT] pres_ex {pres_ex_id} tidak ditemukan. holder punya: {ids}")
                # list credentials untuk debug cred_id
                try:
                    creds = client.list_credentials()
                    cred_ids = [c.get("referent") or c.get("cred_id") or str(c)[:50] for c in creds[:3]]
                except Exception:
                    cred_ids = []
                return jsonify({"error": f"pres_ex_id {pres_ex_id} tidak ditemukan di holder wallet", "detail": detail, "holder_proofs": ids, "available_creds_hint": cred_ids}), 404
            except Exception as ex:
                return jsonify({"error": str(e), "detail": str(ex)}), 500

        # ada cred -> langsung present sinkron (tidak via store)
        if cred_id:
            # validasi cred_id ada di wallet
            cred_check = client.get_credential(cred_id)
            if not cred_check:
                # coba fallback: list dan cek
                pass
            try:
                result = client.send_presentation(pres_ex_id, cred_id=cred_id, referent=referent)
                logger.info(f"✅ [PRESENT] Direct present berhasil untuk {pres_ex_id}")
                return jsonify({"status": "presentation sent", "pres_ex_id": pres_ex_id, "cred_id": cred_id, "result": result}), 200
            except requests.RequestException as e:
                detail = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
                logger.error(f"❌ [PRESENT] Direct present gagal: {detail}")
                return jsonify({"error": "Gagal send presentation", "detail": detail, "pres_ex_id": pres_ex_id, "cred_id": cred_id}), 400
        # jika tanpa cred, simpan untuk auto job
        credential_store.set_for_pres(pres_ex_id, cred_id or "custom_credential_id_123", referent)
        return jsonify({"status": "pres_ex_id disimpan, menunggu auto-present", "pres_ex_id": pres_ex_id}), 200

    # Jika ada cred_id -> simpan ke store (flow connection_id)
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
    """Debug & management untuk credential_store + proxy ke ACA-Py wallet credentials."""
    if request.method == "GET":
        # jika ?acapy=true, proxy ke ACA-Py /credentials untuk dapat cred_id valid
        if request.args.get("acapy") == "true":
            client = AcapyClient()
            try:
                creds = client.list_credentials()
                return jsonify({"results": creds}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        from app.config import settings

        global_cred, _ = credential_store.get_global()
        return jsonify({"global_cred_id": global_cred, "fallback_env": settings.INDY_CRED_ID}), 200
    if request.method == "DELETE":
        credential_store.clear()
        return jsonify({"status": "cleared"}), 200
    # POST sama dengan /present
    return trigger_auto_present()


@bp.route("/simulate/acapy/proofs", methods=["GET"])
def list_proofs():
    """Expose holder proofs untuk k6 debug: GET /present-proof-2.0/records -> filter request-received"""
    client = AcapyClient()
    try:
        proofs = client.list_proofs()
        # filter untuk debug
        filtered = [p for p in proofs if p.get("state") == "request-received"]
        return jsonify({"results": proofs, "request_received": filtered}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
