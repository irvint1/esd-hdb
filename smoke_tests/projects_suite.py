from smoke_tests.common import expect_equal
from smoke_tests.common import expect_true
from smoke_tests.common import request_json
from smoke_tests.common import run_test_suite


def run(base_url):
    projects_base = base_url.rstrip("/")

    def test_get_all_projects(step):
        status, payload = request_json("GET", f"{projects_base}/projects")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_equal(step, "Project count", len(payload["data"]), 20)

    def test_get_one_project(step):
        status, payload = request_json("GET", f"{projects_base}/projects/1")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Project id", payload["data"]["project_id"], 1)
        expect_equal(step, "Project name", payload["data"]["project_name"], "Tengah Garden Walk")
        expect_equal(step, "Project town", payload["data"]["town"], "Tengah")

    def test_get_projects_by_exercise(step):
        status, payload = request_json("GET", f"{projects_base}/exercises/1/projects")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Project count for exercise 1", len(payload["data"]), 7)
        expect_true(
            step,
            "Exercise 1 contains expected projects",
            {1, 2}.issubset({project["project_id"] for project in payload["data"]}),
        )

    return run_test_suite(
        "Projects Smoke Test",
        f"{projects_base}/projects",
        [
            ("GET /projects", test_get_all_projects),
            ("GET /projects/<project_id>", test_get_one_project),
            ("GET /exercises/<exercise_id>/projects", test_get_projects_by_exercise),
        ],
    )
