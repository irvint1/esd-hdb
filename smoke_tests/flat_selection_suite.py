from smoke_tests.common import expect_equal
from smoke_tests.common import request_json
from smoke_tests.common import run_test_suite


def run(base_url):
    selection_base = base_url.rstrip("/")

    def test_get_all_flat_selections(step):
        status, payload = request_json("GET", f"{selection_base}/flat-selection")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Flat selection record count", len(payload["data"]), 4)

    def test_get_one_flat_selection(step):
        status, payload = request_json("GET", f"{selection_base}/flat-selection/1")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Selection id", payload["data"]["selection_id"], 1)
        expect_equal(step, "Selection 1 initial status", payload["data"]["status"], "balloted")

    def test_update_selection_status_and_restore(step):
        changed = False
        try:
            status, payload = request_json(
                "PUT",
                f"{selection_base}/flat-selection/2/status",
                {"status": "selecting"},
            )
            expect_equal(step, "Update status HTTP status", status, 200)
            expect_equal(step, "Selection 2 status after update", payload["data"]["status"], "selecting")
            changed = True

            status, payload = request_json("GET", f"{selection_base}/flat-selection/2")
            expect_equal(step, "GET /flat-selection/2 after update HTTP status", status, 200)
            expect_equal(step, "Selection 2 readback status", payload["data"]["status"], "selecting")
        finally:
            if changed:
                request_json(
                    "PUT",
                    f"{selection_base}/flat-selection/2/status",
                    {"status": "balloted"},
                )

        status, payload = request_json("GET", f"{selection_base}/flat-selection/2")
        expect_equal(step, "GET /flat-selection/2 after restore HTTP status", status, 200)
        expect_equal(step, "Selection 2 status after restore", payload["data"]["status"], "balloted")

    def test_reserve_and_undo_selection(step):
        reserved = False
        try:
            status, payload = request_json(
                "PUT",
                f"{selection_base}/flat-selection/1/reserve",
                {"flat_id": 1},
            )
            expect_equal(step, "Reserve selection HTTP status", status, 200)
            expect_equal(step, "Selection 1 status after reserve", payload["data"]["status"], "reserved")
            expect_equal(step, "Selection 1 flat_id after reserve", payload["data"]["flat_id"], 1)
            reserved = True

            status, payload = request_json("GET", f"{selection_base}/flat-selection/1")
            expect_equal(step, "GET /flat-selection/1 after reserve HTTP status", status, 200)
            expect_equal(step, "Selection 1 readback status", payload["data"]["status"], "reserved")
        finally:
            if reserved:
                request_json("PUT", f"{selection_base}/flat-selection/1/undo-reserve")

        status, payload = request_json("GET", f"{selection_base}/flat-selection/1")
        expect_equal(step, "GET /flat-selection/1 after undo HTTP status", status, 200)
        expect_equal(step, "Selection 1 status after undo", payload["data"]["status"], "balloted")
        expect_equal(step, "Selection 1 flat_id after undo", payload["data"]["flat_id"], None)

    return run_test_suite(
        "Flat Selection Smoke Test",
        f"{selection_base}/flat-selection",
        [
            ("GET /flat-selection", test_get_all_flat_selections),
            ("GET /flat-selection/<selection_id>", test_get_one_flat_selection),
            ("PUT /flat-selection/<selection_id>/status", test_update_selection_status_and_restore),
            ("PUT /flat-selection/<selection_id>/reserve and /undo-reserve", test_reserve_and_undo_selection),
        ],
    )
