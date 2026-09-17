#!/usr/bin/env python3
"""Interactively delete all ACA-Py proof records before a load test."""

import sys
from typing import Callable

from app.services.acapy_client import AcapyClient


def reset_proofs(
    client: AcapyClient,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    proofs = client.list_proofs()
    proof_ids = [proof.get("pres_ex_id") for proof in proofs if proof.get("pres_ex_id")]
    output_fn(f"Ditemukan {len(proof_ids)} proof record.")

    if not proof_ids:
        output_fn("Proof sudah kosong.")
        return 0

    answer = input_fn("Hapus semua proof? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        output_fn("Dibatalkan. Tidak ada proof yang dihapus.")
        return 0

    failed = [proof_id for proof_id in proof_ids if not client.delete_proof(proof_id)]
    remaining = client.list_proofs()
    remaining_ids = [proof.get("pres_ex_id") for proof in remaining if proof.get("pres_ex_id")]

    if failed or remaining_ids:
        output_fn(
            f"Gagal membersihkan proof: {len(failed)} gagal dihapus, "
            f"{len(remaining_ids)} masih tersisa."
        )
        return 1

    output_fn("Semua proof berhasil dihapus. Total sekarang: 0.")
    return 0


def main() -> int:
    try:
        return reset_proofs(AcapyClient())
    except KeyboardInterrupt:
        print("\nDibatalkan.")
        return 130
    except Exception as exc:
        print(f"Gagal mereset proof: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
