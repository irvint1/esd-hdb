from smoke_tests.common import counts_to_flat_type_map
from smoke_tests.common import counts_to_project_type_map
from smoke_tests.common import expect_equal
from smoke_tests.common import request_json
from smoke_tests.common import run_test_suite


def run(base_url):
    flats_base = base_url.rstrip("/")

    expected_all_counts = {
        "1|2-Room Flexi": 1,
        "1|3-Room": 2,
        "1|4-Room": 3,
        "1|5-Room": 2,
        "2|3-Room": 1,
        "2|3Gen": 1,
        "2|4-Room": 2,
        "2|5-Room": 1,
    }
    expected_project_1_counts = {
        "2-Room Flexi": 1,
        "3-Room": 2,
        "4-Room": 3,
        "5-Room": 2,
    }
    expected_project_2_counts = {
        "3-Room": 1,
        "3Gen": 1,
        "4-Room": 2,
        "5-Room": 1,
    }

    def test_get_all_flats(step):
        status, payload = request_json("GET", f"{flats_base}/flats")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Available flat count", len(payload["data"]), 13)
        expect_equal(step, "Flat payload includes project_id", "project_id" in payload["data"][0], True)
        expect_equal(step, "Flat payload excludes project_name", "project_name" in payload["data"][0], False)
        expect_equal(step, "Flat payload excludes town", "town" in payload["data"][0], False)

    def test_get_flats_by_project(step):
        status, payload = request_json("GET", f"{flats_base}/flats?project_id=1")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Project 1 flat count", len(payload["data"]), 8)
        expect_equal(step, "All returned flats belong to project 1", all(item["project_id"] == 1 for item in payload["data"]), True)

    def test_invalid_project_filter(step):
        status, payload = request_json("GET", f"{flats_base}/flats?project_id=abc")
        expect_equal(step, "HTTP status", status, 400)
        expect_equal(step, "Application code", payload["code"], 400)
        expect_equal(step, "Validation message", payload["message"], "project_id must be a positive integer.")

    def test_get_all_available_counts(step):
        status, payload = request_json("GET", f"{flats_base}/flats/available-counts")
        expect_equal(step, "HTTP status", status, 200)
        actual = counts_to_project_type_map(payload["data"]["counts"])
        expect_equal(step, "All available counts", actual, expected_all_counts)

    def test_get_multiple_project_counts(step):
        status, payload = request_json(
            "GET",
            f"{flats_base}/flats/available-counts/projects",
            {"projectIds": [1, 2]},
        )
        expect_equal(step, "HTTP status", status, 200)
        projects = payload["data"]["projects"]
        expect_equal(step, "Returned project groups", len(projects), 2)
        project_map = {item["projectId"]: counts_to_flat_type_map(item["counts"]) for item in projects}
        expect_equal(step, "Project 1 grouped counts", project_map[1], expected_project_1_counts)
        expect_equal(step, "Project 2 grouped counts", project_map[2], expected_project_2_counts)

    def test_reserve_and_unreserve_flat(step):
        status, payload = request_json("GET", f"{flats_base}/flats/1")
        expect_equal(step, "Initial GET /flats/1 HTTP status", status, 200)
        expect_equal(step, "Initial flat 1 status", payload["data"]["status"], "available")

        reserved = False
        try:
            status, payload = request_json(
                "PUT",
                f"{flats_base}/flats/1/reserve",
                {"applicant_id": "smoke-test-applicant"},
            )
            expect_equal(step, "Reserve flat HTTP status", status, 200)
            expect_equal(step, "Reserve flat application code", payload["code"], 200)
            reserved = True

            status, payload = request_json("GET", f"{flats_base}/flats/1")
            expect_equal(step, "GET /flats/1 after reserve HTTP status", status, 200)
            expect_equal(step, "Flat 1 status after reserve", payload["data"]["status"], "reserved")
            expect_equal(step, "Flat 1 reserved_by after reserve", payload["data"]["reserved_by"], "smoke-test-applicant")
        finally:
            if reserved:
                request_json("PUT", f"{flats_base}/flats/1/unreserve")

        status, payload = request_json("GET", f"{flats_base}/flats/1")
        expect_equal(step, "GET /flats/1 after unreserve HTTP status", status, 200)
        expect_equal(step, "Flat 1 status after unreserve", payload["data"]["status"], "available")
        expect_equal(step, "Flat 1 reserved_by after unreserve", payload["data"]["reserved_by"], None)

        status, payload = request_json(
            "GET",
            f"{flats_base}/flats/available-counts/projects",
            {"projectIds": [1]},
        )
        expect_equal(step, "GET grouped counts after unreserve HTTP status", status, 200)
        actual = counts_to_flat_type_map(payload["data"]["projects"][0]["counts"])
        expect_equal(step, "Project 1 counts after unreserve", actual, expected_project_1_counts)

    return run_test_suite(
        "Flats Smoke Test",
        f"{flats_base}/flats/available-counts",
        [
            ("GET /flats", test_get_all_flats),
            ("GET /flats?project_id=1", test_get_flats_by_project),
            ("GET /flats?project_id=abc", test_invalid_project_filter),
            ("GET /flats/available-counts", test_get_all_available_counts),
            ("GET /flats/available-counts/projects", test_get_multiple_project_counts),
            ("PUT /flats/<flat_id>/reserve and /unreserve", test_reserve_and_unreserve_flat),
        ],
    )
