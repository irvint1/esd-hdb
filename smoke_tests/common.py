import json
import shutil
import textwrap
import time
import urllib.error
import urllib.request


PASS = "\u2705"
FAIL = "\u274c"
INFO = "\U0001f50e"
WAIT = "\u23f3"
DONE = "\U0001f389"
SECTION = "=" * 72


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

    print(f"{indent}{'Expected'.ljust(column_width)}{divider}{'Actual'.ljust(column_width)}")
    print(f"{indent}{('-' * column_width)}{divider}{('-' * column_width)}")

    for index in range(row_count):
        left = expected_lines[index] if index < len(expected_lines) else ""
        right = actual_lines[index] if index < len(actual_lines) else ""
        print(f"{indent}{left.ljust(column_width)}{divider}{right.ljust(column_width)}")


def expect_equal(step, label, actual, expected):
    passed = actual == expected
    step.add_check(label, expected, actual, passed)
    if not passed:
        raise TestFailure(f"{label} did not match")


def expect_true(step, label, actual):
    passed = bool(actual)
    step.add_check(label, True, actual, passed)
    if not passed:
        raise TestFailure(f"{label} did not match")


def print_step_result(step):
    icon = PASS if step.passed else FAIL
    print(f"{icon} {step.name}")
    for check in step.checks:
        check_icon = PASS if check["passed"] else FAIL
        print(f"  {check_icon} {check['label']}")
        if not check["passed"]:
            print_side_by_side(check["expected"], check["actual"])


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


def finalize_results(results, title):
    total = results["passed"] + results["failed"]
    print(SECTION)
    print(f"{DONE} {title}: {results['passed']}/{total} checks passed")
    print("Summary:")
    for step in results["steps"]:
        icon = PASS if step.passed else FAIL
        print(f"  {icon} {step.name}")

    if results["failed"] > 0:
        print(f"{FAIL} {results['failed']} checks failed")
        return False

    print(f"{PASS} Everything looks good")
    return True


def run_test_suite(title, readiness_url, test_steps):
    results = {"passed": 0, "failed": 0, "steps": []}
    print(SECTION)
    print(title)
    print(SECTION)
    wait_for_endpoint(readiness_url)

    for name, fn in test_steps:
        run_step(name, fn, results)

    return finalize_results(results, title)


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
