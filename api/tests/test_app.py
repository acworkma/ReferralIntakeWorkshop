import time

from fastapi.testclient import TestClient

from referral.app import app


def test_synthetic_referral_reaches_human_review():
    with TestClient(app) as client:
        created = client.post(
            "/api/referrals",
            headers={"X-Data-Classification": "synthetic"},
            files={"document": ("synthetic-demo.pdf", b"%PDF synthetic demo", "application/pdf")},
        )
        assert created.status_code == 202
        referral_id = created.json()["id"]

        referral = created.json()
        for _ in range(40):
            referral = client.get(f"/api/referrals/{referral_id}").json()
            if referral["status"] == "needs_review":
                break
            time.sleep(0.05)

        assert referral["status"] == "needs_review"
        assert referral["comparison"]["rows"]

        reviewed = client.post(
            f"/api/referrals/{referral_id}/review",
            params={"approved": "true", "note": "Verified synthetic demonstration."},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved"
