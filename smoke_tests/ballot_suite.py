from smoke_tests.common import expect_equal
from smoke_tests.common import expect_true
from smoke_tests.common import request_json
from smoke_tests.common import run_test_suite


def run(base_url):
    ballot_base = base_url.rstrip("/")

    def test_invalid_request(step):
        status, payload = request_json("GET", f"{ballot_base}/ballot/run-bucket", {})
        expect_equal(step, "HTTP status", status, 400)
        expect_equal(step, "Application code", payload["code"], 400)
        expect_true(step, "Validation errors returned", len(payload["message"]) > 0)

    def test_run_ballot(step):
        request_body = {
            "exerciseId": 1,
            "projectIds": [1, 2],
            "flatType": "4-Room",
            "availableCount": 2,
            "applications": [
                {"applicationId": 101, "finalChances": 1},
                {"applicationId": 102, "finalChances": 2, "ballotScheme": "MCPS"},
                {"applicationId": 103, "finalChances": 1},
            ],
        }
        status, payload = request_json("GET", f"{ballot_base}/ballot/run-bucket", request_body)
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Exercise id", payload["data"]["exerciseId"], 1)
        expect_equal(step, "Project ids", payload["data"]["projectIds"], [1, 2])
        expect_equal(step, "Flat type", payload["data"]["flatType"], "4-Room")
        expect_equal(step, "Available count", payload["data"]["availableCount"], 2)
        expect_equal(step, "Max queue size", payload["data"]["maxQueueSize"], 4)
        expect_equal(step, "Shortlisted count", payload["data"]["shortlistedCount"], 3)
        expect_equal(step, "Unsuccessful count", payload["data"]["unsuccessfulCount"], 0)
        expect_equal(step, "Result count", len(payload["data"]["results"]), 3)
        expect_true(
            step,
            "All applications preserved",
            sorted(item["applicationId"] for item in payload["data"]["results"]) == [101, 102, 103],
        )

    return run_test_suite(
        "Ballot Smoke Test",
        f"{ballot_base}/ballot/run-bucket",
        [
            ("GET /ballot/run-bucket invalid request", test_invalid_request),
            ("GET /ballot/run-bucket valid request", test_run_ballot),
        ],
    )
