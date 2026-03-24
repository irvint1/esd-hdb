import argparse
import json
import shutil
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request


PASS = "\u2705"
FAIL = "\u274c"
INFO = "\U0001f50e"
WAIT = "\u23f3"
DONE = "\U0001f389"


class TestFailure(Exception):
    pass


class StepResult:
    def __init__(self, name):
        self.name = name
        self.passed = True
        self.checks = []

    def add_check(self, label, expected, actual, passed):
        self.checks.append(
            {
                "label": label,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
        )
        if not passed:
            self.passed = False


def request_json(method, url, body=None, timeout=10):
    data = None
    headers = {}

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload)
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        return error.code, parsed


def wait_for_endpoint(url, timeout_seconds=60):
    print(f"{WAIT} Waiting for {url}")
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            status, _ = request_json("GET", url, timeout=5)
            if status < 500:
                print(f"{PASS} {url} is reachable")
                return
        except Exception:
            pass

        time.sleep(2)

    raise TestFailure(f"Timed out waiting for {url}")


def pretty(value):
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def split_for_column(value, width, max_lines=8):
    raw = pretty(value)
    lines = raw.splitlines() or [raw]
    wrapped_lines = []

    for line in lines:
        current = textwrap.wrap(
            line,
            width=width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        wrapped_lines.extend(current or [""])

    if len(wrapped_lines) > max_lines:
        remaining = len(wrapped_lines) - max_lines + 1
        wrapped_lines = wrapped_lines[: max_lines - 1] + [f"... (+{remaining} more lines)"]

    return wrapped_lines


def print_side_by_side(expected, actual, indent="     "):
    terminal_width = shutil.get_terminal_size((120, 20)).columns
    available_width = max(60, terminal_width - len(indent))
    divider = " | "
    column_width = max(20, (available_width - len(divider)) // 2)

    expected_lines = split_for_column(expected, column_width)
    actual_lines = split_for_column(actual, column_width)
    row_count = max(len(expected_lines), len(actual_lines))

    print(
        f"{indent}{'Expected'.ljust(column_width)}{divider}{'Actual'.ljust(column_width)}"
    )
    print(
        f"{indent}{('-' * column_width)}{divider}{('-' * column_width)}"
    )

    for index in range(row_count):
        left = expected_lines[index] if index < len(expected_lines) else ""
        right = actual_lines[index] if index < len(actual_lines) else ""
        print(f"{indent}{left.ljust(column_width)}{divider}{right.ljust(column_width)}")


def expect_equal(step, label, actual, expected):
    passed = actual == expected
    step.add_check(label, expected, actual, passed)
    if not passed:
        raise TestFailure(f"{label} did not match")


def print_step_result(step):
    icon = PASS if step.passed else FAIL
    print(f"{icon} {step.name}")
    for check in step.checks:
        check_icon = PASS if check["passed"] else FAIL
        print(f"  {check_icon} {check['label']}")
        print_side_by_side(check["expected"], check["actual"])


def counts_to_project_type_map(counts):
    result = {}
    for item in counts:
        key = f"{item['projectId']}|{item['flatType']}"
        result[key] = item["availableCount"]
    return result


def counts_to_flat_type_map(counts):
    result = {}
    for item in counts:
        result[item["flatType"]] = item["availableCount"]
    return result


def run_step(name, fn, results):
    print(f"{INFO} {name}")
    step = StepResult(name)

    try:
        fn(step)
        print_step_result(step)
        results["passed"] += 1
    except Exception as error:
        if not step.checks:
            step.add_check("Unexpected error", "no exception", str(error), False)
        print_step_result(step)
        print(f"  {FAIL} reason: {error}")
        results["failed"] += 1

    results["steps"].append(step)
    print()


def main():
    parser = argparse.ArgumentParser(description="Smoke-test the flat availability and flat selection APIs.")
    parser.add_argument("--availability-base-url", default="http://localhost:6006")
    parser.add_argument("--selection-base-url", default="http://localhost:6005")
    args = parser.parse_args()

    availability_base = args.availability_base_url.rstrip("/")
    selection_base = args.selection_base_url.rstrip("/")

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

    results = {"passed": 0, "failed": 0, "steps": []}

    wait_for_endpoint(f"{availability_base}/flats/available-counts")
    wait_for_endpoint(f"{selection_base}/flat-selection")

    def test_get_all_flats(step):
        status, payload = request_json("GET", f"{availability_base}/flats")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Available flat count", len(payload["data"]), 13)

    def test_get_all_available_counts(step):
        status, payload = request_json("GET", f"{availability_base}/flats/available-counts")
        expect_equal(step, "HTTP status", status, 200)
        actual = counts_to_project_type_map(payload["data"]["counts"])
        expect_equal(step, "All available counts", actual, expected_all_counts)

    def test_get_project_available_counts(step):
        status, payload = request_json("GET", f"{availability_base}/flats/available-counts/1")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Project id", payload["data"]["projectId"], 1)
        actual = counts_to_flat_type_map(payload["data"]["counts"])
        expect_equal(step, "Project 1 counts", actual, expected_project_1_counts)

    def test_get_project_available_counts_with_filter(step):
        flat_type = urllib.parse.quote("4-Room")
        status, payload = request_json("GET", f"{availability_base}/flats/available-counts/1?flat_type={flat_type}")
        expect_equal(step, "HTTP status", status, 200)
        actual = counts_to_flat_type_map(payload["data"]["counts"])
        expect_equal(step, "Filtered project 1 counts", actual, {"4-Room": 3})

    def test_post_multiple_project_counts(step):
        status, payload = request_json(
            "POST",
            f"{availability_base}/flats/available-counts/projects",
            {"projectIds": [1, 2]},
        )
        expect_equal(step, "HTTP status", status, 200)

        projects = payload["data"]["projects"]
        expect_equal(step, "Returned project groups", len(projects), 2)

        project_map = {item["projectId"]: counts_to_flat_type_map(item["counts"]) for item in projects}
        expect_equal(step, "Project 1 grouped counts", project_map[1], expected_project_1_counts)
        expect_equal(step, "Project 2 grouped counts", project_map[2], expected_project_2_counts)

    def test_reserve_and_unreserve_flat(step):
        status, payload = request_json("GET", f"{availability_base}/flats/1")
        expect_equal(step, "Initial GET /flats/1 HTTP status", status, 200)
        expect_equal(step, "Initial flat 1 status", payload["data"]["status"], "available")

        reserved = False
        try:
            status, payload = request_json(
                "PUT",
                f"{availability_base}/flats/1/reserve",
                {"applicant_id": "smoke-test-applicant"},
            )
            expect_equal(step, "Reserve flat HTTP status", status, 200)
            expect_equal(step, "Reserve flat application code", payload["code"], 200)
            reserved = True

            status, payload = request_json("GET", f"{availability_base}/flats/1")
            expect_equal(step, "GET /flats/1 after reserve HTTP status", status, 200)
            expect_equal(step, "Flat 1 status after reserve", payload["data"]["status"], "reserved")
            expect_equal(step, "Flat 1 reserved_by after reserve", payload["data"]["reserved_by"], "smoke-test-applicant")

            status, payload = request_json("GET", f"{availability_base}/flats/available-counts/1")
            expect_equal(step, "GET project counts after reserve HTTP status", status, 200)
            actual = counts_to_flat_type_map(payload["data"]["counts"])
            expected_after_reserve = dict(expected_project_1_counts)
            expected_after_reserve["4-Room"] = 2
            expect_equal(step, "Project 1 counts after reserve", actual, expected_after_reserve)
        finally:
            if reserved:
                request_json("PUT", f"{availability_base}/flats/1/unreserve")

        status, payload = request_json("GET", f"{availability_base}/flats/1")
        expect_equal(step, "GET /flats/1 after unreserve HTTP status", status, 200)
        expect_equal(step, "Flat 1 status after unreserve", payload["data"]["status"], "available")
        expect_equal(step, "Flat 1 reserved_by after unreserve", payload["data"]["reserved_by"], None)

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

    test_steps = [
        ("GET /flats", test_get_all_flats),
        ("GET /flats/available-counts", test_get_all_available_counts),
        ("GET /flats/available-counts/<project_id>", test_get_project_available_counts),
        ("GET /flats/available-counts/<project_id>?flat_type=...", test_get_project_available_counts_with_filter),
        ("POST /flats/available-counts/projects", test_post_multiple_project_counts),
        ("PUT /flats/<flat_id>/reserve and /unreserve", test_reserve_and_unreserve_flat),
        ("GET /flat-selection", test_get_all_flat_selections),
        ("GET /flat-selection/<selection_id>", test_get_one_flat_selection),
        ("PUT /flat-selection/<selection_id>/status", test_update_selection_status_and_restore),
        ("PUT /flat-selection/<selection_id>/reserve and /undo-reserve", test_reserve_and_undo_selection),
    ]

    for name, fn in test_steps:
        run_step(name, fn, results)

    total = results["passed"] + results["failed"]
    print(f"{DONE} Smoke test complete: {results['passed']}/{total} checks passed")
    print("Summary:")
    for step in results["steps"]:
        icon = PASS if step.passed else FAIL
        print(f"  {icon} {step.name}")

    if results["failed"] > 0:
        print(f"{FAIL} {results['failed']} checks failed")
        sys.exit(1)

    print(f"{PASS} Everything looks good")


if __name__ == "__main__":
    main()
