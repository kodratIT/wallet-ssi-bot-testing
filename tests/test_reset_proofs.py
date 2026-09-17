from scripts.reset_proofs import reset_proofs


class FakeClient:
    def __init__(self, proof_ids):
        self.proof_ids = list(proof_ids)
        self.deleted = []

    def list_proofs(self):
        return [{"pres_ex_id": proof_id} for proof_id in self.proof_ids]

    def delete_proof(self, proof_id):
        self.deleted.append(proof_id)
        self.proof_ids.remove(proof_id)
        return True


def test_reset_proofs_requires_confirmation():
    client = FakeClient(["proof-1", "proof-2"])
    output = []

    result = reset_proofs(client, input_fn=lambda _: "n", output_fn=output.append)

    assert result == 0
    assert client.deleted == []
    assert client.proof_ids == ["proof-1", "proof-2"]
    assert "Dibatalkan" in output[-1]


def test_reset_proofs_deletes_and_verifies_empty():
    client = FakeClient(["proof-1", "proof-2"])

    result = reset_proofs(client, input_fn=lambda _: "y", output_fn=lambda _: None)

    assert result == 0
    assert client.deleted == ["proof-1", "proof-2"]
    assert client.proof_ids == []
