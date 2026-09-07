import time

from fastapi.testclient import TestClient

from referral.app import app


def _deliver(client: TestClient, name: str, body: bytes):
    return client.post("/api/referrals", files={"document": (name, body, "application/pdf")})


def _await_referral(client: TestClient, filename: str) -> dict:
    """The API no longer returns a referral: the pipeline is what creates it."""
    for _ in range(100):
        rows = client.get("/api/referrals").json()
        match = next((row for row in rows if row["filename"] == filename), None)
        if match:
            return match
        time.sleep(0.05)
    raise AssertionError(f"{filename} never appeared in the review queue.")


def _await_status(client: TestClient, referral_id: str, status: str) -> dict:
    referral: dict = {}
    for _ in range(100):
        referral = client.get(f"/api/referrals/{referral_id}").json()
        if referral.get("status") == status:
            return referral
        time.sleep(0.05)
    return referral


def test_a_document_delivered_to_the_landing_zone_reaches_human_review():
    with TestClient(app) as client:
        delivered = _deliver(client, "demo.pdf", b"%PDF demo document")
        assert delivered.status_code == 202
        # The response describes a delivery, not a referral. Nothing exists yet:
        # the blob write is what starts the workflow.
        assert delivered.json()["container"] == "incoming"
        assert "id" not in delivered.json()

        referral = _await_status(client, _await_referral(client, "demo.pdf")["id"], "needs_review")
        assert referral["status"] == "needs_review"
        assert referral["comparison"]["rows"]
        assert referral["submittedBy"]

        reviewed = client.post(
            f"/api/referrals/{referral['id']}/review",
            params={"approved": "true", "note": "Verified demonstration."},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved"


def test_deleting_a_referral_allows_redelivering_the_same_document():
    body = b"%PDF resubmission document"
    with TestClient(app) as client:
        assert _deliver(client, "resubmit.pdf", body).status_code == 202
        referral = _await_status(
            client, _await_referral(client, "resubmit.pdf")["id"], "needs_review"
        )

        assert _deliver(client, "resubmit.pdf", body).status_code == 409

        assert client.delete(f"/api/referrals/{referral['id']}").status_code == 204
        assert client.get(f"/api/referrals/{referral['id']}").status_code == 404
        assert client.delete(f"/api/referrals/{referral['id']}").status_code == 404

        assert _deliver(client, "resubmit.pdf", body).status_code == 202


def test_health_reports_which_landing_zone_is_in_use():
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["landingZone"] in {"azure", "local"}
