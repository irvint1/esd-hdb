import datetime

from smoke_tests.common import expect_equal
from smoke_tests.common import expect_true
from smoke_tests.common import request_json
from smoke_tests.common import run_test_suite


def run(base_url):
    audits_base = base_url.rstrip("/")

    def test_get_all_ballot_audits(step):
        status, payload = request_json("GET", f"{audits_base}/ballot-audits")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Audit record count", len(payload["data"]), 3)

    def test_create_and_update_audit(step):
        run_at = datetime.datetime.now().replace(microsecond=0).isoformat()
        created_id = None

        status, payload = request_json(
            "POST",
            f"{audits_base}/ballot-audits",
            {
                "exercise_id": 99,
                "run_at": run_at,
                "status": "in progress",
            },
        )
        expect_equal(step, "Create audit HTTP status", status, 201)
        created_id = payload["data"]["audit_id"]
        expect_equal(step, "Created audit exercise id", payload["data"]["exercise_id"], 99)
        expect_equal(step, "Created audit status", payload["data"]["status"], "in progress")

        status, payload = request_json(
            "PUT",
            f"{audits_base}/ballot-audits/{created_id}",
            {"status": "completed"},
        )
        expect_equal(step, "Update audit HTTP status", status, 200)
        expect_equal(step, "Updated audit status", payload["data"]["status"], "completed")
        expect_true(step, "Audit id preserved", payload["data"]["audit_id"] == created_id)

    return run_test_suite(
        "Ballot Audits Smoke Test",
        f"{audits_base}/ballot-audits",
        [
            ("GET /ballot-audits", test_get_all_ballot_audits),
            ("POST/PUT /ballot-audits", test_create_and_update_audit),
        ],
    )
