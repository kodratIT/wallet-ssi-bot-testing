import logging
from typing import Optional

import requests

from app.config import settings
from app.extensions import http_session

logger = logging.getLogger(__name__)


class AcapyClient:
    """
    Encapsulasi semua call ke ACA-Py.
    Reusable: bisa dipakai dari route maupun background job.
    Testable: session bisa di-inject mock.
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.base_url = settings.ACA_PY_URL.rstrip("/")
        self.headers = settings.aca_py_headers
        self.verify = settings.ACA_PY_VERIFY_SSL
        self.timeout = settings.ACA_PY_TIMEOUT
        self.session = session or http_session

    def receive_invitation(self, invitation: dict) -> str:
        """
        POST /out-of-band/receive-invitation
        Returns: connection_id
        Raises: requests.RequestException / ValueError jika tanpa connection_id
        """
        url = f"{self.base_url}/out-of-band/receive-invitation"
        logger.info(f"📨 Mengirim undangan ke ACA-Py: {url}")
        resp = self.session.post(
            url,
            headers=self.headers,
            params={"auto_accept": "true", "use_existing_connection": "false"},
            json=invitation,
            verify=self.verify,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        conn_id = data.get("connection_id")
        if not conn_id:
            raise ValueError("Tidak ada connection_id yang dikembalikan dari ACA-Py")
        logger.info(f"✅ Connection ID: {conn_id}")
        return conn_id

    def list_proofs(self) -> list:
        """GET /present-proof-2.0/records"""
        url = f"{self.base_url}/present-proof-2.0/records"
        resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("results", [])
    def list_connections(self) -> list:
        """GET /connections"""
        url = f"{self.base_url}/connections"
        resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def get_proof(self, pres_ex_id: str) -> dict:
        """GET /present-proof-2.0/records/{pres_ex_id}"""
        url = f"{self.base_url}/present-proof-2.0/records/{pres_ex_id}"
        resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def send_presentation(self, pres_ex_id: str, cred_id: Optional[str] = None, referent: Optional[str] = None) -> dict:
        """
        POST /present-proof-2.0/records/{pres_ex_id}/send-presentation
        Auto-detect requested_attributes dari proof record agar semua referent terisi (bukan cuma 1).
        """
        url = f"{self.base_url}/present-proof-2.0/records/{pres_ex_id}/send-presentation"
        cred_id = cred_id or settings.INDY_CRED_ID
        # referent hint dari k6, tapi akan di-override jika proof minta banyak atribut
        requested_referent = referent or settings.INDY_ATTR_REFERENT

        # Coba ambil detail proof untuk tahu requested_attributes yang diminta verifier
        requested_attrs = {}
        try:
            proof = self.get_proof(pres_ex_id)
            # by_format.pres_request.indy.requested_attributes atau pres_request.orig
            # ACA-Py v2: proof.pres_request -> {indy: {requested_attributes: {attr1_referent: {name, restrictions}}, ...}}
            pres_req = proof.get("pres_request") or proof.get("by_format", {}).get("pres_request", {})
            indy_req = pres_req.get("indy") or {}
            if not indy_req:
                # fallback: proof.by_format.pres_request.indy
                indy_req = proof.get("by_format", {}).get("pres_request", {}).get("indy", {})
            req_attrs = indy_req.get("requested_attributes") or {}
            if req_attrs:
                for ref in req_attrs.keys():
                    requested_attrs[ref] = {"cred_id": cred_id, "revealed": True}
                logger.info(f"🔍 Proof {pres_ex_id} minta {list(req_attrs.keys())} -> pakai cred {cred_id} untuk semua")
            else:
                logger.warning(f"⚠️ Proof {pres_ex_id} tidak ada requested_attributes, fallback ke {requested_referent}")
        except Exception as e:
            logger.warning(f"⚠️ Gagal fetch proof {pres_ex_id} untuk auto-detect referent: {e}")

        if not requested_attrs:
            requested_attrs = {requested_referent: {"cred_id": cred_id, "revealed": True}}

        payload = {
            "indy": {
                "requested_attributes": requested_attrs,
                "requested_predicates": {},
                "self_attested_attributes": {},
            },
            "auto_remove": True,
        }
        logger.info(f"📤 Mengirim presentasi untuk {pres_ex_id} (cred_id={cred_id} referents={list(requested_attrs.keys())})")
        resp = self.session.post(url, headers=self.headers, json=payload, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def list_credentials(self) -> list:
        """GET /credentials - list wallet credentials (untuk cek cred_id valid)"""
        # ACA-Py endpoint bervariasi: /credentials atau /wallet/credentials
        for path in ["/credentials", "/wallet/credentials", "/credential/wallets", "/present-proof-2.0/records"]:
            try:
                url = f"{self.base_url}{path}"
                resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    # /credentials mengembalikan {"results": [...]}
                    if isinstance(data, dict) and "results" in data:
                        return data["results"]
                    if isinstance(data, list):
                        return data
            except Exception:
                continue
        return []

    def get_credential(self, cred_id: str) -> Optional[dict]:
        """GET /credentials/{cred_id} - cek apakah cred_id ada"""
        for path in [f"/credentials/{cred_id}", f"/wallet/credentials/{cred_id}"]:
            try:
                url = f"{self.base_url}{path}"
                resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
        return None

    def delete_proof(self, pres_ex_id: str) -> bool:
        """DELETE /present-proof-2.0/records/{pres_ex_id}"""
        url = f"{self.base_url}/present-proof-2.0/records/{pres_ex_id}"
        try:
            resp = self.session.delete(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
            resp.raise_for_status()
            logger.info(f"🗑️ Proof {pres_ex_id} dihapus")
            return True
        except requests.RequestException as e:
            logger.warning(f"⚠️ Gagal hapus proof {pres_ex_id}: {e}")
            return False

    def delete_connection(self, connection_id: str) -> bool:
        """DELETE /connections/{connection_id} - untuk cleanup opsional"""
        url = f"{self.base_url}/connections/{connection_id}"
        try:
            resp = self.session.delete(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
            resp.raise_for_status()
            logger.info(f"🗑️ Connection {connection_id} dihapus")
            return True
        except requests.RequestException as e:
            logger.warning(f"⚠️ Gagal hapus connection {connection_id}: {e}")
            return False
