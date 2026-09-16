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

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.ACA_PY_URL).rstrip("/")
        token = settings.ACA_PY_TOKEN if token is None else token
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"
        self.verify = settings.ACA_PY_VERIFY_SSL
        self.timeout = settings.ACA_PY_TIMEOUT
        self.session = session or http_session

    def receive_invitation(self, invitation: dict) -> dict:
        """
        POST /out-of-band/receive-invitation
        Returns: {"connection_id": str|None, "oob_id": str|None, "mode": "connection"|"connectionless"}
        - OOB connection (ada handshake_protocols): ACA-Py mengembalikan connection_id.
        - OOB connectionless (hanya requests~attach present-proof, tanpa handshake):
          TIDAK ada connection_id, hanya oob_id. Ini normal — holder yang sudah
          auto-respond-presentation-request akan langsung mempresentasi.
        Raises: requests.RequestException / ValueError jika keduanya kosong.
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
        oob_id = data.get("oob_id") or data.get("invitation_id")
        if not conn_id and not oob_id:
            raise ValueError("ACA-Py tidak mengembalikan connection_id maupun oob_id")
        mode = "connection" if conn_id else "connectionless"
        logger.info(f"✅ Undangan diterima mode={mode} connection_id={conn_id} oob_id={oob_id}")
        return {"connection_id": conn_id, "oob_id": oob_id, "mode": mode}

    def list_proofs(self) -> list:
        """GET /present-proof-2.0/records"""
        url = f"{self.base_url}/present-proof-2.0/records"
        resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("results", [])
    def list_connections(self, invitation_msg_id: Optional[str] = None) -> list:
        """GET /connections, optionally scoped to an OOB invitation."""
        url = f"{self.base_url}/connections"
        params = {"invitation_msg_id": invitation_msg_id} if invitation_msg_id else None
        resp = self.session.get(url, headers=self.headers, params=params, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def get_proof(self, pres_ex_id: str) -> dict:
        """GET /present-proof-2.0/records/{pres_ex_id}"""
        url = f"{self.base_url}/present-proof-2.0/records/{pres_ex_id}"
        resp = self.session.get(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    def find_credential_by_schema(self, schema_id: str) -> Optional[str]:
        """Return an ACA-Py credential referent matching the Indy schema ID."""
        if not schema_id:
            return None
        for item in self.list_credentials():
            credential = item.get("cred_info", item) if isinstance(item, dict) else {}
            if credential.get("schema_id") == schema_id:
                return credential.get("referent") or credential.get("cred_id")
        return None


    def send_presentation(self, pres_ex_id: str, cred_id: Optional[str] = None, referent: Optional[str] = None) -> dict:
        """
        POST /present-proof-2.0/records/{pres_ex_id}/send-presentation
        Auto-detect requested_attributes dari proof record agar semua referent terisi (bukan cuma 1).
        """
        url = f"{self.base_url}/present-proof-2.0/records/{pres_ex_id}/send-presentation"
        if cred_id is None:
            cred_id = settings.INDY_CRED_ID
            if cred_id == "custom_credential_id_123":
                cred_id = self.find_credential_by_schema(settings.INDY_SCHEMA_ID)
        if not cred_id:
            raise ValueError(
                f"No ACA-Py credential found for schema {settings.INDY_SCHEMA_ID}"
            )
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
        """DELETE /connections/{connection_id}; a missing record is already clean."""
        url = f"{self.base_url}/connections/{connection_id}"
        try:
            resp = self.session.delete(url, headers=self.headers, verify=self.verify, timeout=self.timeout)
            if resp.status_code == 404:
                return True
            resp.raise_for_status()
            logger.info(f"🗑️ Connection {connection_id} dihapus")
            return True
        except requests.RequestException as e:
            logger.warning(f"⚠️ Gagal hapus connection {connection_id}: {e}")
            return False
