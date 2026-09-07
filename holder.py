import base64
import json
import time
import threading
import requests
import logging
import os
import urllib.parse
import urllib3
import logging
import time

from flask import Flask, request, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Inisialisasi aplikasi Flask
app = Flask(__name__)

# Konfigurasi logging: Log akan ditampilkan di konsol dengan format timestamp, level, dan pesan.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- KONFIGURASI GLOBAL ---
# Mengambil nilai dari environment variables atau menggunakan nilai default.
# PASTIKAN NILAI-NILAI INI SESUAI DENGAN LINGKUNGAN ANDA!
# Anda dapat mengatur environment variables ini sebelum menjalankan aplikasi, contoh:
# export ACA_PY_URL="https://your-acapy-agent.com:7844"
# export ACA_PY_TOKEN="your_aca_py_admin_token"
# export WALT_ID_TOKEN="your_walt_id_bearer_token"

ACA_PY_URL = os.getenv("ACA_PY_URL", "https://agent-admin.srvhub.biz.id:7844")
# ACA_PY_TOKEN = os.getenv("ACA_PY_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ3YWxsZXRfaWQiOiIzNzM3NzQ1MC01M2E2LTRjZDgtODdlNC1lNTFlZjliOTQxM2IiLCJpYXQiOjE3NDg4MjI4OTR9.FNQutXPfYbpC7fsLe1BWqHK9ruq56F0mCzO7PTyn_bc")
ACA_PY_TOKEN = os.getenv("ACA_PY_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ3YWxsZXRfaWQiOiJiNTFjMzI2ZC05YjBlLTRjZWYtOWI5ZC0zMTVkODZiNmZiMjUiLCJpYXQiOjE3NDkwODMwMjF9.jtWv9gNQsYYYZHwPesLSmpxR1pK-O4a6vPlwYsUYBFE")
WALT_ID_TOKEN = os.getenv("WALT_ID_TOKEN", "Bearer eyJhbGciOiJIUzI1NiJ9.eyJuYmYiOjE3NDgzNTc5NzksImV4cCI6MTc1MDk0OTk3OSwiaWF0IjoxNzQ4MzU3OTc5LCJqdGkiOiJlNWU1NmU4MC02N2Y5LTQyMTQtYTA2MC0wYjc2NGQ4YTNmODIiLCJpc3MiOiJodHRwOi8vbG9jYWxob3N0OjcwMDEiLCJhdWQiOiJodHRwOi8vbG9jYWxob3N0OjcwMDEiLCJzdWIiOiIwYTM1MDllMi0xMzliLTRjMWItYWFlOC0xMjhmOGE4NzAyYTgifQ.2BvnHcIjwtmqUIILIHjdhYlP-1YsBa5iXCGJgiin9zM")

WALT_WALLET_API_BASE = "https://wallet.taspenjambi.site:7844"
WALLET_ID = "3066e565-f9e9-4c53-b89c-eaf175afc6f2"

# Headers default untuk request ke ACA-Py
DEFAULT_HEADERS = {"Content-Type": "application/json"}
if ACA_PY_TOKEN:
    DEFAULT_HEADERS["Authorization"] = f"Bearer {ACA_PY_TOKEN}"

# --- FUNGSI PEMBANTU (HELPER FUNCTIONS) ---

def decode_base64_invitation(raw_body: str) -> dict:
    """
    Mendekode body undangan yang dienkode base64url.
    Akan menambahkan padding jika diperlukan.
    """
    logging.info("🔍 Mencoba mendekode undangan base64url...")
    try:
        # Tambahkan padding jika diperlukan untuk decoding base64url
        padded = raw_body + '=' * (-len(raw_body) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded.encode('utf-8'))
        invitation = json.loads(decoded_bytes.decode('utf-8'))
        logging.info(f"📦 Undangan berhasil didekode (JSON):\n{json.dumps(invitation, indent=2)}")
        return invitation
    except Exception as e:
        logging.error(f"❌ Gagal mendekode undangan base64: {e}")
        # Angkat ValueError agar bisa ditangkap di rute Flask dan mengembalikan response 400
        raise ValueError(f"Gagal mendekode OOB ACA-Py: {e}")

# def delete_old_proof_records():
#     """
#     Menghapus record proof lama dari ACA-Py.
#     Berguna untuk membersihkan state sebelum memulai test baru.
#     """
#     logging.info("🧹 Mengambil daftar proof lama dari v2.0...")
#     try:
#         response = requests.get(f"{ACA_PY_URL}/present-proof-2.0/records",
#                                 headers=DEFAULT_HEADERS,
#                                 verify=False) # PERINGATAN: verify=False tidak aman untuk produksi!
        
#         # Mengangkat HTTPError untuk respons yang buruk (4xx atau 5xx)
#         response.raise_for_status() 
#         old_proofs = response.json().get("results", [])
#         logging.info(f"📋 Ditemukan {len(old_proofs)} proof lama")

#         for p in old_proofs:
#             record_id = p.get("pres_ex_id")
#             if not record_id:
#                 logging.warning("⚠️ Proof tanpa pres_ex_id, dilewati.")
#                 continue

#             delete_url = f"{ACA_PY_URL}/present-proof-2.0/records/{record_id}"
#             try:
#                 del_res = requests.delete(delete_url,
#                                           headers=DEFAULT_HEADERS,
#                                           verify=False) # PERINGATAN: verify=False tidak aman untuk produksi!
#                 del_res.raise_for_status() # Angkat HTTPError jika penghapusan gagal
#                 logging.info(f"🗑️ Berhasil menghapus proof {record_id}")
#             except requests.exceptions.HTTPError as e:
#                 if e.response.status_code == 404:
#                     logging.warning(f"❌ Proof {record_id} tidak ditemukan (404).")
#                 else:
#                     logging.error(f"⚠️ Gagal menghapus proof {record_id}: {e.response.status_code} - {e.response.text}")
#             except requests.exceptions.RequestException as e:
#                 logging.error(f"🚨 Error saat menghapus proof {record_id}: {e}")

#     except requests.exceptions.HTTPError as e:
#         logging.error(f"⚠️ Gagal mengambil proof lama: status={e.response.status_code} - {e.response.text}")
#     except requests.exceptions.RequestException as e:
#         logging.error(f"🚨 Exception saat mengambil/menghapus proof lama: {e}")


# def auto_present_job():
#     """
#     Memantau secara terus-menerus semua permintaan proof (proof request)
#     dan mengirimkan presentasi (presentation) secara otomatis.
#     Fungsi ini berjalan dalam satu thread terpisah di background.
#     """
#     logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")

#     poll_interval_sec = 2  # Interval polling dalam detik
#     processed_proof_ids = set()  # Untuk proof yang berhasil diproses
#     pending_proof_ids = {}       # Untuk proof yang baru saja dikirim presentasinya
#     SEND_DELAY_SEC = 10          # Delay untuk menghindari pengiriman ganda

#     while True:
#         time.sleep(poll_interval_sec)
#         logging.info(f"🔁 [AUTO] Polling untuk proof request baru...")

#         now = time.time()
#         # Hapus proof_id dari pending_proof_ids jika sudah lewat delay
#         expired_ids = [pid for pid, ts in pending_proof_ids.items() if now - ts > SEND_DELAY_SEC]
#         for pid in expired_ids:
#             pending_proof_ids.pop(pid, None)

#         try:
#             response = requests.get(
#                 f"{ACA_PY_URL}/present-proof-2.0/records",
#                 headers=DEFAULT_HEADERS,
#                 verify=False  # PERINGATAN: Tidak aman untuk produksi
#             )
#             response.raise_for_status()
#             proofs = response.json().get("results", [])
#         except requests.exceptions.RequestException as e:
#             logging.error(f"❌ Error saat mengambil proof records dari ACA-Py: {e}")
#             continue

#         for proof in proofs:
#             proof_id = proof.get("pres_ex_id")
#             state = proof.get("state")

#             if state != "request-received":
#                 # Jika status bukan request-received, bersihkan dari pending
#                 processed_proof_ids.discard(proof_id)
#                 pending_proof_ids.pop(proof_id, None)
#                 continue

#             if proof_id in processed_proof_ids:
#                 continue  # Sudah diproses sukses

#             if proof_id in pending_proof_ids:
#                 logging.debug(f"⏳ [AUTO] Menunggu delay untuk proof ID: {proof_id}, skip sementara.")
#                 continue  # Baru saja dikirim, tunggu ACA-Py update state

#             logging.info(f"🎯 [AUTO] Proof request ditemukan dengan ID: {proof_id}, state: {state}")
#             pending_proof_ids[proof_id] = now  # Tandai sebagai sedang dikirim

#             # GANTI payload ini sesuai proof request dan credential Anda
#             payload = {
#                 "indy": {
#                     "requested_attributes": {
#                         "attr1_referent": {
#                             "cred_id": "custom_credential_id_123",  # GANTI DENGAN YANG SESUAI
#                             "revealed": True
#                         }
#                     },
#                     "requested_predicates": {},
#                     "self_attested_attributes": {}
#                 },
#                 "auto_remove": True
#             }

#             logging.info(f"📤 [AUTO] Mengirim presentasi untuk proof ID: {proof_id}")
#             try:
#                 res = requests.post(
#                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
#                     headers=DEFAULT_HEADERS,
#                     json=payload,
#                     verify=False
#                 )
#                 res.raise_for_status()
#                 logging.info(f"✅ [AUTO] Presentation berhasil dikirim untuk proof ID: {proof_id}")
#                 processed_proof_ids.add(proof_id)
#                 pending_proof_ids.pop(proof_id, None)  # Bersihkan setelah sukses
#             except requests.exceptions.RequestException as e:
#                 logging.error(f"❌ [AUTO] Gagal mengirim presentation untuk {proof_id}: {e}")
#                 if hasattr(e, 'response') and e.response is not None:
#                     logging.error(f"Detail error respons: {e.response.status_code} - {e.response.text}")
#                 # Hapus dari pending agar bisa dicoba lagi
#                 pending_proof_ids.pop(proof_id, None)

# from concurrent.futures import ThreadPoolExecutor, as_completed

# def delete_proof_record(proof_id, state):
#     try:
#         url = f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}"
#         logging.info(f"🧹 [AUTO] Menghapus proof ID: {proof_id}, state: {state}")
#         del_res = requests.delete(
#             url,
#             headers=DEFAULT_HEADERS,
#             verify=False
#         )
#         del_res.raise_for_status()
#         logging.info(f"✅ [AUTO] Proof ID {proof_id} berhasil dihapus (state: {state}, status_code: {del_res.status_code})")
#     except requests.exceptions.RequestException as e:
#         if hasattr(e, 'response') and e.response is not None:
#             logging.warning(
#                 f"⚠️ [AUTO] Gagal menghapus proof ID {proof_id} (state: {state}) "
#                 f"→ status_code: {e.response.status_code}, reason: {e.response.text}"
#             )
#         else:
#             logging.warning(f"⚠️ [AUTO] Gagal menghapus proof ID {proof_id}: {e}")

# def auto_present_job():
#     """
#     Memantau permintaan proof dan secara otomatis mengirim presentasi.
#     - Cleanup awal satu kali saat startup
#     - Cleanup proof yang 'abandoned'
#     - Kirim presentasi otomatis untuk 'request-received'
#     - Hindari duplikat pengiriman (race-safe)
#     """
#     logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")

#     poll_interval_sec = 2
#     processed_proof_ids = set()
#     pending_proof_ids = {}
#     SEND_DELAY_SEC = 10
#     first_run = True

#     while True:
#         if first_run:
#             # 🔥 Cleanup awal satu kali
#             try:
#                 logging.info("🧹 [AUTO-FIRST-RUN] Cleanup awal proof records...")
#                 cleanup_res = requests.get(
#                     f"{ACA_PY_URL}/present-proof-2.0/records",
#                     headers=DEFAULT_HEADERS,
#                     verify=False
#                 )
#                 cleanup_res.raise_for_status()
#                 all_proofs = cleanup_res.json().get("results", [])

#                 proofs_to_delete = [
#                     (p.get("pres_ex_id"), p.get("state"))
#                     for p in all_proofs
#                     if p.get("state") not in ["done", "abandoned", "verified", "presentation-sent"]
#                 ]

#                 if proofs_to_delete:
#                     logging.info(f"🔍 [AUTO-FIRST-RUN] {len(proofs_to_delete)} proof records akan dihapus.")
#                     with ThreadPoolExecutor(max_workers=10) as executor:
#                         futures = [
#                             executor.submit(delete_proof_record, pid, state)
#                             for pid, state in proofs_to_delete
#                         ]
#                         for future in as_completed(futures):
#                             future.result()
#                 else:
#                     logging.info("✅ [AUTO-FIRST-RUN] Tidak ada proof record yang perlu dihapus.")

#             except Exception as e:
#                 logging.error(f"❌ [AUTO-FIRST-RUN] Gagal melakukan cleanup awal: {e}")

#             first_run = False

#         time.sleep(poll_interval_sec)
#         logging.info("🔁 [AUTO] Polling untuk proof request baru...")

#         now = time.time()
#         expired_ids = [pid for pid, ts in pending_proof_ids.items() if now - ts > SEND_DELAY_SEC]
#         for pid in expired_ids:
#             pending_proof_ids.pop(pid, None)

#         try:
#             response = requests.get(
#                 f"{ACA_PY_URL}/present-proof-2.0/records",
#                 headers=DEFAULT_HEADERS,
#                 verify=False
#             )
#             response.raise_for_status()
#             proofs = response.json().get("results", [])
#         except requests.exceptions.RequestException as e:
#             logging.error(f"❌ Error saat mengambil proof records dari ACA-Py: {e}")
#             continue

#         # 🔄 Hapus proof dengan state 'abandoned' saat polling
#         for proof in proofs:
#             if proof.get("state") == "abandoned":
#                 proof_id = proof.get("pres_ex_id")
#                 logging.info(f"🧹 [AUTO] Proof ID {proof_id} dalam state 'abandoned'. Akan dihapus.")
#                 delete_proof_record(proof_id, "abandoned")

#         # Filter hanya 'request-received' untuk dikirim presentasi
#         proofs = [p for p in proofs if p.get("state") == "request-received"]

#         for proof in proofs:
#             proof_id = proof.get("pres_ex_id")
#             state = proof.get("state")

#             if proof_id in processed_proof_ids or proof_id in pending_proof_ids:
#                 continue

#             if state != "request-received":
#                 continue

#             logging.info(f"🎯 [AUTO] Proof request ditemukan dengan ID: {proof_id}, state: {state}")
#             pending_proof_ids[proof_id] = now

#             # GANTI payload ini sesuai proof request & kredensial
#             payload = {
#                 "indy": {
#                     "requested_attributes": {
#                         "attr1_referent": {
#                             "cred_id": "custom_credential_id_123",  # GANTI sesuai data wallet Anda
#                             "revealed": True
#                         }
#                     },
#                     "requested_predicates": {},
#                     "self_attested_attributes": {}
#                 },
#                 "auto_remove": True
#             }

#             logging.info(f"📤 [AUTO] Mengirim presentasi untuk proof ID: {proof_id}")
#             try:
#                 res = requests.post(
#                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
#                     headers=DEFAULT_HEADERS,
#                     json=payload,
#                     verify=False
#                 )
#                 res.raise_for_status()
#                 logging.info(f"✅ [AUTO] Presentation berhasil dikirim untuk proof ID: {proof_id}")
#                 processed_proof_ids.add(proof_id)
#                 pending_proof_ids.pop(proof_id, None)
#             except requests.exceptions.RequestException as e:
#                 logging.error(f"❌ [AUTO] Gagal mengirim presentation untuk {proof_id}: {e}")
#                 if hasattr(e, 'response') and e.response is not None:
#                     logging.error(f"Detail error respons: {e.response.status_code} - {e.response.text}")
#                 pending_proof_ids.pop(proof_id, None)

# def auto_present_job():
#     """
#     Memantau secara terus-menerus semua permintaan proof (proof request)
#     dan mengirimkan presentasi (presentation) secara otomatis.
#     Fungsi ini berjalan dalam satu thread terpisah di background.
#     """
#     logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")

#     poll_interval_sec = 2 # Interval polling dalam detik
    
#     # Set untuk melacak proof_id yang sedang atau sudah diproses
#     # Ini untuk menghindari reprocessing yang tidak perlu jika state ACA-Py lambat berubah
#     processed_proof_ids = set() 

#     while True:
#         time.sleep(poll_interval_sec)
#         logging.info(f"🔁 [AUTO] Polling untuk proof request baru...")

#         try:
#             response = requests.get(f"{ACA_PY_URL}/present-proof-2.0/records",
#                                     headers=DEFAULT_HEADERS,
#                                     verify=False) # PERINGATAN: verify=False tidak aman untuk produksi!
#             response.raise_for_status()
#             proofs = response.json().get("results", [])
#         except requests.exceptions.RequestException as e:
#             logging.error(f"❌ Error saat mengambil proof records dari ACA-Py: {e}")
#             continue # Lanjutkan ke iterasi berikutnya jika ada error

#         for proof in proofs:
#             proof_id = proof.get("pres_ex_id")
#             state = proof.get("state")

#             # Hanya proses proof yang berstatus 'request-received' dan belum pernah diproses
#             if state == "request-received" and proof_id not in processed_proof_ids:
#                 logging.info(f"🎯 [AUTO] Proof request ditemukan dengan ID: {proof_id}, state: {state}")
#                 processed_proof_ids.add(proof_id) # Tambahkan ke set agar tidak diproses lagi segera

#                 logging.info(f"✅ Proof request siap diproses: {proof_id}")

#                 # PENTING: Sesuaikan payload ini berdasarkan proof request yang sebenarnya dan kredensial Anda.
#                 # Anda perlu mengetahui atribut apa yang diminta dan memiliki cred_id yang sesuai.
#                 # Periksa payload proof request di ACA-Py Admin API untuk mengetahui referent apa yang diminta.
#                 payload = {
#                     "indy": {
#                         "requested_attributes": {
#                             # Contoh: 'attr1_referent' adalah nama atribut yang diminta dalam proof request.
#                             # GANTI "YOUR_ACTUAL_CREDENTIAL_ID_HERE" dengan ID KREDENSIAL ASLI Anda dari ACA-Py Wallet!
#                             # Anda bisa mendapatkan cred_id ini dari GET /wallet/credentials atau dari log saat penerbitan.
#                             "attr1_referent": { # <--- GANTI 'attr1_referent' jika nama atributnya berbeda di proof request
#                                 "cred_id": "custom_credential_id_123", # <--- WAJIB GANTI INI!
#                                 "revealed": True
#                             }
#                         },
#                         "requested_predicates": {}, # Tambahkan predicates jika diminta
#                         "self_attested_attributes": {} # Tambahkan self-attested attributes jika diminta
#                     },
#                     "auto_remove": True # Akan menghapus record setelah berhasil
#                 }

#                 logging.info(f"📤 [AUTO] Mengirim presentasi untuk proof ID: {proof_id}")
#                 try:
#                     res = requests.post(
#                         f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
#                         headers=DEFAULT_HEADERS,
#                         json=payload,
#                         verify=False # PERINGATAN: verify=False tidak aman untuk produksi!
#                     )
#                     res.raise_for_status()
#                     logging.info(f"✅ [AUTO] Presentation berhasil dikirim untuk proof ID: {proof_id}")
#                     # Jika berhasil, ACA-Py akan mengubah state, jadi tidak perlu dihapus dari processed_proof_ids
#                 except requests.exceptions.RequestException as e:
#                     logging.error(f"❌ [AUTO] Gagal mengirim presentation untuk {proof_id}: {e}")
#                     if hasattr(e, 'response') and e.response is not None:
#                         logging.error(f"Detail error respons: {e.response.status_code} - {e.response.text}")
#                     # Jika gagal, hapus dari processed_proof_ids agar bisa dicoba lagi di iterasi berikutnya
#                     processed_proof_ids.discard(proof_id) 
#             elif state != "request-received" and proof_id in processed_proof_ids:
#                 # Jika state sudah berubah (misal 'presentation-sent', 'verified', dll),
#                 # dan proof_id ada di set processed_proof_ids, berarti sudah selesai diproses.
#                 # Hapus dari set untuk membersihkan memori.
#                 processed_proof_ids.discard(proof_id)


# def auto_present_job():
#     """
#     Memantau semua permintaan proof (request-received) dan mengirim presentasi hanya sekali.
#     Jika state sudah 'presentation-sent' atau lainnya, tidak akan dikirim ulang.
#     """
#     logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")

#     poll_interval_sec = 2
#     processed_proof_ids = set()

#     while True:
#         time.sleep(poll_interval_sec)
#         logging.info("🔁 [AUTO] Polling untuk proof request baru...")

#         try:
#             response = requests.get(
#                 f"{ACA_PY_URL}/present-proof-2.0/records",
#                 headers=DEFAULT_HEADERS,
#                 verify=False
#             )
#             response.raise_for_status()
#             proofs = response.json().get("results", [])
#         except requests.exceptions.RequestException as e:
#             logging.error(f"❌ Error saat mengambil proof records dari ACA-Py: {e}")
#             continue

#         for proof in proofs:
#             proof_id = proof.get("pres_ex_id")
#             state = proof.get("state")

#             if not proof_id:
#                 continue

#             if proof_id in processed_proof_ids:
#                 # Sudah pernah diproses, lewati
#                 continue

#             if state != "request-received":
#                 # Hanya proses proof yang benar-benar baru
#                 continue

#             logging.info(f"🎯 [AUTO] Proof baru: {proof_id}, state: {state}")
#             processed_proof_ids.add(proof_id)

#             payload = {
#                 "indy": {
#                     "requested_attributes": {
#                         "attr1_referent": {
#                             "cred_id": "custom_credential_id_123",  # Ganti sesuai kredensial Anda
#                             "revealed": True
#                         }
#                     },
#                     "requested_predicates": {},
#                     "self_attested_attributes": {}
#                 },
#                 "auto_remove": True
#             }

#             logging.info(f"📤 Mengirim presentation untuk proof ID: {proof_id}")
#             try:
#                 res = requests.post(
#                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
#                     headers=DEFAULT_HEADERS,
#                     json=payload,
#                     verify=False
#                 )
#                 res.raise_for_status()
#                 logging.info(f"✅ Presentation berhasil dikirim untuk proof ID: {proof_id}")
#             except requests.exceptions.RequestException as e:
#                 logging.error(f"❌ Gagal kirim presentation: {proof_id}: {e}")
#                 if hasattr(e, 'response') and e.response is not None:
#                     logging.error(f"🧾 Detail error: {e.response.status_code} - {e.response.text}")
#                 processed_proof_ids.discard(proof_id)  # Boleh dicoba ulang nanti

#         # Opsional: bersihkan proof_id yang state-nya sudah bukan "request-received"
#         active_ids = set(p.get("pres_ex_id") for p in proofs if p.get("state") == "request-received")
#         processed_proof_ids = {pid for pid in processed_proof_ids if pid in active_ids}


# def delete_proof_record(proof_id, state):
#     try:
#         url = f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}"
#         logging.info(f"🧹 [AUTO] Menghapus proof ID: {proof_id}, state: {state}")
#         del_res = requests.delete(
#             url,
#             headers=DEFAULT_HEADERS,
#             verify=False
#         )
#         del_res.raise_for_status()
#         logging.info(f"✅ [AUTO] Proof ID {proof_id} berhasil dihapus (state: {state})")
#     except requests.exceptions.RequestException as e:
#         if hasattr(e, 'response') and e.response is not None:
#             logging.warning(
#                 f"⚠️ [AUTO] Gagal menghapus proof ID {proof_id} (state: {state}) "
#                 f"→ status_code: {e.response.status_code}, reason: {e.response.text}"
#             )
#         else:
#             logging.warning(f"⚠️ [AUTO] Gagal menghapus proof ID {proof_id}: {e}")

# # def auto_present_job():
# #     logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")
# #     poll_interval_sec = 2
# #     SEND_DELAY_SEC = 2  # ⏳ Delay sebelum auto-send agar tidak bentrok dengan manual

# #     processed_proof_ids = set()
# #     pending_proof_ids = {}
# #     first_run = True

# #     while True:
# #         if first_run:
# #             try:
# #                 logging.info("🧹 [AUTO-FIRST-RUN] Cleanup awal proof records...")
# #                 cleanup_res = requests.get(
# #                     f"{ACA_PY_URL}/present-proof-2.0/records",
# #                     headers=DEFAULT_HEADERS,
# #                     verify=False
# #                 )
# #                 cleanup_res.raise_for_status()
# #                 all_proofs = cleanup_res.json().get("results", [])

# #                 proofs_to_delete = [
# #                     (p.get("pres_ex_id"), p.get("state"))
# #                     for p in all_proofs
# #                     if p.get("state") == "abandoned"
# #                 ]

# #                 if proofs_to_delete:
# #                     logging.info(f"🔍 [AUTO-FIRST-RUN] {len(proofs_to_delete)} proof records akan dihapus.")
# #                     with ThreadPoolExecutor(max_workers=10) as executor:
# #                         futures = [
# #                             executor.submit(delete_proof_record, pid, state)
# #                             for pid, state in proofs_to_delete
# #                         ]
# #                         for future in as_completed(futures):
# #                             future.result()
# #                 else:
# #                     logging.info("✅ [AUTO-FIRST-RUN] Tidak ada proof record yang perlu dihapus.")
# #             except Exception as e:
# #                 logging.error(f"❌ [AUTO-FIRST-RUN] Gagal melakukan cleanup awal: {e}")

# #             first_run = False

# #         time.sleep(poll_interval_sec)
# #         logging.info("🔁 [AUTO] Polling untuk proof request baru...")

# #         now = time.time()
# #         expired_ids = [pid for pid, ts in pending_proof_ids.items() if now - ts > SEND_DELAY_SEC + 5]
# #         for pid in expired_ids:
# #             pending_proof_ids.pop(pid, None)

# #         try:
# #             response = requests.get(
# #                 f"{ACA_PY_URL}/present-proof-2.0/records",
# #                 headers=DEFAULT_HEADERS,
# #                 verify=False
# #             )
# #             response.raise_for_status()
# #             proofs = response.json().get("results", [])
# #         except requests.exceptions.RequestException as e:
# #             logging.error(f"❌ Gagal mengambil proof records dari ACA-Py: {e}")
# #             continue

# #         for proof in proofs:
# #             state = proof.get("state")
# #             proof_id = proof.get("pres_ex_id")

# #             if state == "abandoned":
# #                 logging.info(f"🧹 [AUTO] Proof ID {proof_id} dalam state 'abandoned'. Akan dihapus.")
# #                 delete_proof_record(proof_id, "abandoned")
# #                 continue

# #             if state != "request-received":
# #                 continue

# #             if proof_id in processed_proof_ids:
# #                 continue

# #             now = time.time()

# #             if proof_id not in pending_proof_ids:
# #                 # Pertama kali ditemukan, catat waktu
# #                 pending_proof_ids[proof_id] = now
# #                 logging.info(f"🕒 [AUTO] Menunggu {SEND_DELAY_SEC}s untuk proof ID: {proof_id}")
# #                 continue

# #             # Jika belum cukup delay, skip dulu
# #             if now - pending_proof_ids[proof_id] < SEND_DELAY_SEC:
# #                 continue

# #             # 🔁 Cek ulang state terbaru dari proof
# #             try:
# #                 check_res = requests.get(
# #                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}",
# #                     headers=DEFAULT_HEADERS,
# #                     verify=False
# #                 )
# #                 check_res.raise_for_status()
# #                 current_state = check_res.json().get("state")
# #                 if current_state != "request-received":
# #                     logging.warning(f"⏭️ Proof ID {proof_id} tidak dalam state 'request-received' lagi (state: {current_state})")
# #                     pending_proof_ids.pop(proof_id, None)
# #                     continue
# #             except requests.exceptions.RequestException as e:
# #                 logging.warning(f"⚠️ Gagal cek ulang proof ID {proof_id}: {e}")
# #                 pending_proof_ids.pop(proof_id, None)
# #                 continue

# #             logging.info(f"🎯 [AUTO] Proof request ditemukan dengan ID: {proof_id}, state: {state}")
# #             logging.info(f"📤 [AUTO] Mengirim presentasi untuk proof ID: {proof_id}")

# #             payload = {
# #                 "indy": {
# #                     "requested_attributes": {
# #                         "attr1_referent": {
# #                             "cred_id": "custom_credential_id_123",  # 🔧 Ganti sesuai kredensial kamu
# #                             "revealed": True
# #                         }
# #                     },
# #                     "requested_predicates": {},
# #                     "self_attested_attributes": {}
# #                 },
# #                 "auto_remove": True
# #             }

# #             try:
# #                 res = requests.post(
# #                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
# #                     headers=DEFAULT_HEADERS,
# #                     json=payload,
# #                     verify=False
# #                 )
# #                 res.raise_for_status()
# #                 logging.info(f"✅ [AUTO] Presentation berhasil dikirim untuk proof ID: {proof_id}")
# #                 processed_proof_ids.add(proof_id)
# #                 pending_proof_ids.pop(proof_id, None)
# #             except requests.exceptions.RequestException as e:
# #                 logging.error(f"❌ [AUTO] Gagal mengirim presentation untuk {proof_id}: {e}")
# #                 if hasattr(e, 'response') and e.response is not None:
# #                     logging.error(f"Detail error respons: {e.response.status_code} - {e.response.text}")
# #                 pending_proof_ids.pop(proof_id, None)
# def delete_connection_record(connection_id):
#     try:
#         url = f"{ACA_PY_URL}/connections/{connection_id}"
#         logging.info(f"🧹 [AUTO] Menghapus koneksi ID: {connection_id}")
#         del_res = requests.delete(
#             url,
#             headers=DEFAULT_HEADERS,
#             verify=False
#         )
#         del_res.raise_for_status()
#         logging.info(f"✅ [AUTO] Koneksi ID {connection_id} berhasil dihapus")
#     except requests.exceptions.RequestException as e:
#         if hasattr(e, 'response') and e.response is not None:
#             logging.warning(
#                 f"⚠️ Gagal menghapus koneksi ID {connection_id} → "
#                 f"status_code: {e.response.status_code}, reason: {e.response.text}"
#             )
#         else:
#             logging.warning(f"⚠️ Gagal menghapus koneksi ID {connection_id}: {e}")

# def auto_present_job():
#     logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")
#     poll_interval_sec = 1
#     SEND_DELAY_SEC = 1

#     processed_proof_ids = set()
#     pending_proof_ids = {}
#     first_run = True

#     while True:
#         if first_run:
#             try:
#                 logging.info("🧹 [AUTO-FIRST-RUN] Cleanup awal proof records...")
#                 cleanup_res = requests.get(
#                     f"{ACA_PY_URL}/present-proof-2.0/records",
#                     headers=DEFAULT_HEADERS,
#                     verify=False
#                 )
#                 cleanup_res.raise_for_status()
#                 all_proofs = cleanup_res.json().get("results", [])

#                 proofs_to_delete = [
#                     (p.get("pres_ex_id"), p.get("state"))
#                     for p in all_proofs
#                     if p.get("state") == "abandoned"
#                 ]

#                 if proofs_to_delete:
#                     logging.info(f"🔍 [AUTO-FIRST-RUN] {len(proofs_to_delete)} proof records akan dihapus.")
#                     with ThreadPoolExecutor(max_workers=10) as executor:
#                         futures = [
#                             executor.submit(delete_proof_record, pid, state)
#                             for pid, state in proofs_to_delete
#                         ]
#                         for future in as_completed(futures):
#                             future.result()
#                 else:
#                     logging.info("✅ [AUTO-FIRST-RUN] Tidak ada proof record yang perlu dihapus.")
#             except Exception as e:
#                 logging.error(f"❌ [AUTO-FIRST-RUN] Gagal melakukan cleanup awal: {e}")

#             first_run = False

#         time.sleep(poll_interval_sec)
#         logging.info("🔁 [AUTO] Polling untuk proof request baru...")

#         now = time.time()
#         expired_ids = [pid for pid, ts in pending_proof_ids.items() if now - ts > SEND_DELAY_SEC + 5]
#         for pid in expired_ids:
#             pending_proof_ids.pop(pid, None)

#         try:
#             response = requests.get(
#                 f"{ACA_PY_URL}/present-proof-2.0/records",
#                 headers=DEFAULT_HEADERS,
#                 verify=False
#             )
#             response.raise_for_status()
#             proofs = response.json().get("results", [])
#         except requests.exceptions.RequestException as e:
#             logging.error(f"❌ Gagal mengambil proof records dari ACA-Py: {e}")
#             continue

#         for proof in proofs:
#             state = proof.get("state")
#             proof_id = proof.get("pres_ex_id")

#             if state == "abandoned":
#                 logging.info(f"🧹 [AUTO] Proof ID {proof_id} dalam state 'abandoned'. Akan dihapus.")
#                 delete_proof_record(proof_id, "abandoned")
#                 continue

#             # elif state == "done":
#             #     connection_id = proof.get("connection_id")
#             #     if not connection_id:
#             #         logging.warning(f"⚠️ Proof ID {proof_id} tidak punya connection_id. Skip hapus koneksi.")
#             #         continue

#             #     logging.info(f"🧹 [AUTO] Presentation selesai untuk proof ID {proof_id}. Menghapus koneksi {connection_id}...")

#             #     try:
#             #         del_conn_res = requests.delete(
#             #             f"{ACA_PY_URL}/connections/{connection_id}",
#             #             headers=DEFAULT_HEADERS,
#             #             verify=False
#             #         )
#             #         del_conn_res.raise_for_status()
#             #         logging.info(f"✅ [AUTO] Koneksi {connection_id} berhasil dihapus setelah proof ID {proof_id}")
#             #     except requests.exceptions.RequestException as e:
#             #         if hasattr(e, 'response') and e.response is not None:
#             #             logging.warning(
#             #                 f"⚠️ Gagal hapus koneksi {connection_id} setelah proof ID {proof_id} selesai → "
#             #                 f"status: {e.response.status_code}, reason: {e.response.text}"
#             #             )
#             #         else:
#             #             logging.warning(f"⚠️ Gagal hapus koneksi {connection_id}: {e}")
#             #     continue

#             if state != "request-received":
#                 continue

#             if proof_id in processed_proof_ids:
#                 continue

#             now = time.time()

#             if proof_id not in pending_proof_ids:
#                 pending_proof_ids[proof_id] = now
#                 logging.info(f"🕒 [AUTO] Menunggu {SEND_DELAY_SEC}s untuk proof ID: {proof_id}")
#                 continue

#             if now - pending_proof_ids[proof_id] < SEND_DELAY_SEC:
#                 continue

#             try:
#                 check_res = requests.get(
#                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}",
#                     headers=DEFAULT_HEADERS,
#                     verify=False
#                 )
#                 check_res.raise_for_status()
#                 current_state = check_res.json().get("state")
#                 if current_state != "request-received":
#                     logging.warning(f"⏭️ Proof ID {proof_id} tidak dalam state 'request-received' lagi (state: {current_state})")
#                     pending_proof_ids.pop(proof_id, None)
#                     continue
#             except requests.exceptions.RequestException as e:
#                 logging.warning(f"⚠️ Gagal cek ulang proof ID {proof_id}: {e}")
#                 pending_proof_ids.pop(proof_id, None)
#                 continue

#             logging.info(f"🎯 [AUTO] Proof request ditemukan dengan ID: {proof_id}, state: {state}")
#             logging.info(f"📤 [AUTO] Mengirim presentasi untuk proof ID: {proof_id}")

#             payload = {
#                 "indy": {
#                     "requested_attributes": {
#                         "attr1_referent": {
#                             "cred_id": "custom_credential_id_123",
#                             "revealed": True
#                         }
#                     },
#                     "requested_predicates": {},
#                     "self_attested_attributes": {}
#                 },
#                 "auto_remove": True
#             }

#             try:
#                 res = requests.post(
#                     f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
#                     headers=DEFAULT_HEADERS,
#                     json=payload,
#                     verify=False
#                 )
#                 res.raise_for_status()
#                 logging.info(f"✅ [AUTO] Presentation berhasil dikirim untuk proof ID: {proof_id}")
#                 processed_proof_ids.add(proof_id)
#                 pending_proof_ids.pop(proof_id, None)
#             except requests.exceptions.RequestException as e:
#                 logging.error(f"❌ [AUTO] Gagal mengirim presentation untuk {proof_id}: {e}")
#                 if hasattr(e, 'response') and e.response is not None:
#                     logging.error(f"Detail error respons: {e.response.status_code} - {e.response.text}")
#                 pending_proof_ids.pop(proof_id, None)



def delete_proof_record(proof_id, state):
    try:
        url = f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}"
        logging.info(f"🧹 Menghapus proof ID: {proof_id} (state: {state})")
        res = requests.delete(url, headers=DEFAULT_HEADERS, verify=False)
        res.raise_for_status()
        logging.info(f"✅ Proof ID {proof_id} berhasil dihapus")
    except requests.exceptions.RequestException as e:
        logging.warning(f"⚠️ Gagal hapus proof ID {proof_id}: {e}")


def auto_present_job():
    logging.info("👁️ [AUTO] Memulai pemantauan proof request global.")
    poll_interval_sec = 5
    SEND_DELAY_SEC = 2

    processed_proof_ids = set()
    pending_proof_ids = {}
    first_run = True

    while True:
        if first_run:
            try:
                logging.info("🧹 [AUTO-FIRST-RUN] Cleanup awal SEMUA proof records...")
                cleanup_res = requests.get(
                    f"{ACA_PY_URL}/present-proof-2.0/records",
                    headers=DEFAULT_HEADERS,
                    verify=False
                )
                cleanup_res.raise_for_status()
                all_proofs = cleanup_res.json().get("results", [])

                proofs_to_delete = [
                    (p.get("pres_ex_id"), p.get("state"))
                    for p in all_proofs
                ]

                if proofs_to_delete:
                    logging.info(f"🔍 [AUTO-FIRST-RUN] {len(proofs_to_delete)} proof records akan dihapus.")
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = [
                            executor.submit(delete_proof_record, pid, state)
                            for pid, state in proofs_to_delete
                        ]
                        for future in as_completed(futures):
                            future.result()
                else:
                    logging.info("✅ [AUTO-FIRST-RUN] Tidak ada proof record yang perlu dihapus.")
            except Exception as e:
                logging.error(f"❌ [AUTO-FIRST-RUN] Gagal melakukan cleanup awal: {e}")

            first_run = False

        time.sleep(poll_interval_sec)
        logging.info("🔁 [AUTO] Polling untuk proof request baru...")

        now = time.time()
        expired_ids = [pid for pid, ts in pending_proof_ids.items() if now - ts > SEND_DELAY_SEC + 5]
        for pid in expired_ids:
            pending_proof_ids.pop(pid, None)

        try:
            response = requests.get(
                f"{ACA_PY_URL}/present-proof-2.0/records",
                headers=DEFAULT_HEADERS,
                verify=False
            )
            response.raise_for_status()
            proofs = response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Gagal mengambil proof records dari ACA-Py: {e}")
            continue

        for proof in proofs:
            state = proof.get("state")
            proof_id = proof.get("pres_ex_id")

            if state != "request-received":
                continue

            if proof_id in processed_proof_ids:
                continue

            now = time.time()

            if proof_id not in pending_proof_ids:
                pending_proof_ids[proof_id] = now
                logging.info(f"🕒 [AUTO] Menunggu {SEND_DELAY_SEC}s untuk proof ID: {proof_id}")
                continue

            if now - pending_proof_ids[proof_id] < SEND_DELAY_SEC:
                continue

            # 🔁 Cek ulang state sebelum kirim
            try:
                check_res = requests.get(
                    f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}",
                    headers=DEFAULT_HEADERS,
                    verify=False
                )
                check_res.raise_for_status()
                current_state = check_res.json().get("state")

                if current_state != "request-received":
                    logging.warning(f"⏭️ Proof ID {proof_id} tidak dalam state 'request-received' lagi (state: {current_state})")
                    pending_proof_ids.pop(proof_id, None)
                    continue

            except requests.exceptions.RequestException as e:
                logging.warning(f"⚠️ Gagal cek ulang proof ID {proof_id}: {e}")
                pending_proof_ids.pop(proof_id, None)
                continue

            logging.info(f"🎯 [AUTO] Proof request ditemukan dengan ID: {proof_id}, state: {state}")
            logging.info(f"📤 [AUTO] Mengirim presentasi untuk proof ID: {proof_id}")

            payload = {
                "indy": {
                    "requested_attributes": {
                        "attr1_referent": {
                            "cred_id": "custom_credential_id_123",  # GANTI dengan cred_id valid
                            "revealed": True
                        }
                    },
                    "requested_predicates": {},
                    "self_attested_attributes": {}
                },
                "auto_remove": True
            }

            try:
                res = requests.post(
                    f"{ACA_PY_URL}/present-proof-2.0/records/{proof_id}/send-presentation",
                    headers=DEFAULT_HEADERS,
                    json=payload,
                    verify=False
                )
                res.raise_for_status()
                logging.info(f"✅ [AUTO] Presentation berhasil dikirim untuk proof ID: {proof_id}")
                processed_proof_ids.add(proof_id)
                pending_proof_ids.pop(proof_id, None)
            except requests.exceptions.RequestException as e:
                logging.error(f"❌ [AUTO] Gagal mengirim presentation untuk {proof_id}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logging.error(f"Detail error respons: {e.response.status_code} - {e.response.text}")
                pending_proof_ids.pop(proof_id, None)
# --- RUTE FLASK ---

@app.route("/simulate/acapy/receive", methods=["POST"])
def receive_acapy_invitation():
    """
    Menerima undangan Out-of-Band (OOB) yang dienkode base64url.
    Mendekode undangan, lalu mengirimkannya ke ACA-Py untuk diterima.
    Proses presentasi proof selanjutnya akan ditangani oleh background thread 'auto_present_job'.
    """
    logging.info("🛬 [RECEIVE] Permintaan penerimaan undangan diterima.")
    raw_body = request.get_data(as_text=True)
    logging.info(f"🔍 [RECEIVE] Raw body undangan: {raw_body}")

    try:
        invitation = decode_base64_invitation(raw_body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    logging.info("📨 [RECEIVE] Mengirim undangan yang diterima ke ACA-Py...")
    try:
        res = requests.post(f"{ACA_PY_URL}/out-of-band/receive-invitation",
                            headers=DEFAULT_HEADERS, json=invitation, verify=False) # PERINGATAN: verify=False tidak aman untuk produksi!
        res.raise_for_status() # Akan mengangkat HTTPError untuk status code 4xx/5xx
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ [RECEIVE] Gagal menerima undangan di ACA-Py: {e}")
        detail_error = str(e)
        if hasattr(e, 'response') and e.response is not None:
            detail_error = e.response.text
        return jsonify({"error": "Gagal menerima undangan oleh ACA-Py", "detail": detail_error}), 500

    conn_id = res.json().get("connection_id")
    if not conn_id:
        logging.error("❌ [RECEIVE] Tidak ada 'connection_id' yang dikembalikan dari ACA-Py.")
        return jsonify({"error": "Tidak ada connection_id yang dikembalikan dari ACA-Py"}), 500

    logging.info(f"✅ [RECEIVE] Connection ID berhasil dibuat: {conn_id}. Background thread akan memproses proof request.")

    return jsonify({"status": "undangan diterima dan proses auto-present akan dimulai oleh background thread", "connection_id": conn_id}), 200

@app.route("/simulate/acapy/present", methods=["POST"])
def trigger_auto_present():
    """
    Endpoint ini bisa digunakan untuk memicu pengecekan segera oleh background thread.
    Atau, jika Anda ingin memicu presentasi untuk connection_id tertentu secara manual,
    Anda bisa menambahkan logika queuing di sini yang akan diproses oleh background thread.
    Saat ini, ini hanya berfungsi sebagai konfirmasi bahwa background thread aktif.
    
    Contoh body POST request:
    Untuk memicu polling umum: `{}`
    Untuk mengindikasikan connection_id (saat ini tidak ada logika prioritas): `{"connection_id": "some-connection-id"}`
    Pastikan Content-Type: application/json
    """
    logging.info("🔄 [TRIGGER] Permintaan untuk memicu auto-present diterima.")

    # Opsi: Hapus proof lama sebelum memicu auto-present (uncomment jika diperlukan untuk testing)
    # delete_old_proof_records()

    try:
        # Mencoba membaca JSON dari body request. silent=True agar tidak raise error
        # jika body kosong atau Content-Type bukan application/json.
        data = request.get_json(silent=True)
        
        conn_id = None
        if data and isinstance(data, dict):
            conn_id = data.get("connection_id")

        if conn_id:
            logging.info(f"🚀 [TRIGGER] Permintaan untuk memicu presentasi (indikasi connection ID: {conn_id}). Background thread akan memprosesnya.")
        else:
            logging.info("🚀 [TRIGGER] Memicu pengecekan background thread untuk semua proof request (tidak ada connection ID spesifik).")
    except Exception as e:
        # Menangkap error jika ada masalah lain saat memproses JSON (misalnya, body tidak bisa di-decode sama sekali)
        logging.warning(f"⚠️ [TRIGGER] Gagal membaca JSON body atau JSON tidak valid: {e}. Melanjutkan tanpa connection_id spesifik.")
        conn_id = None 

    # Karena auto_present_job sudah berjalan secara global dan terus-menerus polling,
    # tidak perlu memulai thread baru di sini. Endpoint ini hanya mengkonfirmasi status.
    return jsonify({"status": "background auto-present thread aktif dan akan memproses proof request", "connection_id": conn_id}), 200

@app.route("/simulate/use-presentation-request", methods=["POST"])
def use_presentation_request():
    try:
        print("🟢 Menerima request POST ke /simulate/use-presentation-request")

        data = request.json
        print(f"📥 Payload dari client: {data}")

        presentation_url = data.get("presentationRequest")
        if not presentation_url:
            print("❌ presentationRequest tidak ditemukan di body")
            return jsonify({"error": "Missing presentationRequest"}), 400

        print(f"🔗 presentationRequest (OID4VP URL): {presentation_url}")

        # Siapkan payload untuk Walt.id Wallet API
        payload = {
            "presentationRequest": presentation_url,  # ini string full "openid4vp://..."
            "selectedCredentials": [
                "urn:uuid:74623a2d-1c67-449e-894d-350550ba4393"
            ],
            "disclosures": None  # <- inilah yang cocok dengan "disclosures": null di curl
        }

        headers = {
            "Authorization": WALT_ID_TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Endpoint Walt.id Wallet API
        url = f"{WALT_WALLET_API_BASE}/wallet-api/wallet/{WALLET_ID}/exchange/usePresentationRequest"
    
        print(f"🌍 Endpoint tujuan: {url}")

        # Kirim request ke Walt.id Wallet API
        print("🚀 Mengirim POST request ke Walt.id Wallet API...")
        response = requests.post(url, json=payload, headers=headers, verify=False)

        print(f"📨 Response status code: {response.status_code}")
        print(f"📨 Response body: {response.text}")

        if response.status_code not in [200, 201]:
            print(f"❌ Gagal kirim usePresentationRequest: {response.status_code}")
            return jsonify({
                "error": "Failed to use presentation request",
                "detail": response.text
            }), 502

        print("✅ usePresentationRequest berhasil")
        return jsonify({
            "status": "success",
            "result": response.json()
        })

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return jsonify({"error": "Exception during process", "detail": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    """
    Rute dasar untuk memeriksa apakah aplikasi aktif.
    """
    return "✅ SSI Simulation Webhook is Active", 200


if __name__ == "__main__":
    # Mulai thread auto_present_job sekali saat aplikasi dimulai.
    # Ini akan berjalan di background secara terus-menerus sebagai daemon thread.
    # Daemon thread akan otomatis berakhir ketika program utama (Flask) berhenti.
   # auto_present_thread = threading.Thread(target=auto_present_job, daemon=True)
    #auto_present_thread.start()
    #logging.info("✅ Background auto-present thread telah dimulai.")

    # Menjalankan aplikasi Flask.
    # Untuk lingkungan produksi, disarankan menggunakan server WSGI seperti Gunicorn (misal: gunicorn -w 4 app:app).
    # Untuk pengembangan lokal:
    app.run(host="0.0.0.0", port=5050, debug=True) # debug=True hanya untuk pengembangan!
