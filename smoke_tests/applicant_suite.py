import time

from smoke_tests.common import expect_equal
from smoke_tests.common import expect_true
from smoke_tests.common import request_json
from smoke_tests.common import run_test_suite


def run(base_url):
    applicant_base = base_url.rstrip("/")

    def test_get_all_applicants(step):
        status, payload = request_json("GET", f"{applicant_base}/applicant")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Application code", payload["code"], 200)
        expect_true(step, "Applicants returned", len(payload["data"]["applicants"]) > 0)

    def test_get_one_applicant(step):
        status, payload = request_json("GET", f"{applicant_base}/applicant/1")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Applicant id", payload["data"]["applicant_id"], 1)
        expect_equal(step, "Applicant NRIC", payload["data"]["nric"], "S8501234A")

    def test_get_applicant_by_nric(step):
        status, payload = request_json("GET", f"{applicant_base}/applicant/nric/S8501234A")
        expect_equal(step, "HTTP status", status, 200)
        expect_equal(step, "Applicant id", payload["data"]["applicant_id"], 1)

    def test_create_update_delete_applicant(step):
        unique_seed = str(time.time_ns())
        nric = f"T{int(unique_seed[-7:]):07d}A"
        mobile_number = f"{int(unique_seed[-8:]):08d}"
        email = f"smoke.{unique_seed}@example.com"
        updated_mobile = f"{(int(mobile_number) + 1) % 100000000:08d}"
        updated_email = f"smoke.updated.{unique_seed}@example.com"

        created_id = None

        try:
            status, payload = request_json(
                "POST",
                f"{applicant_base}/applicant",
                {
                    "nric": nric,
                    "name": "Smoke Test Applicant",
                    "date_of_birth": "1995-01-01",
                    "mobile_number": mobile_number,
                    "email": email,
                    "address": "Smoke Street",
                    "place_of_birth": "Singapore",
                    "race": "Chinese",
                    "nationality": "Singapore",
                    "sex": "Male",
                    "password": "Sm0ke@Test",
                },
            )
            expect_equal(step, "Create applicant HTTP status", status, 201)
            created_id = payload["data"]["applicant_id"]
            expect_equal(step, "Created applicant NRIC", payload["data"]["nric"], nric)

            status, payload = request_json(
                "PUT",
                f"{applicant_base}/applicant/{created_id}",
                {
                    "mobile_number": updated_mobile,
                    "email": updated_email,
                },
            )
            expect_equal(step, "Update applicant HTTP status", status, 200)
            expect_equal(step, "Updated applicant mobile", payload["data"]["mobile_number"], updated_mobile)
            expect_equal(step, "Updated applicant email", payload["data"]["email"], updated_email)

            status, payload = request_json("DELETE", f"{applicant_base}/applicant/{created_id}")
            expect_equal(step, "Delete applicant HTTP status", status, 200)
            expect_equal(step, "Delete applicant application code", payload["code"], 200)
        finally:
            if created_id is not None:
                request_json("DELETE", f"{applicant_base}/applicant/{created_id}")

        status, payload = request_json("GET", f"{applicant_base}/applicant/nric/{nric}")
        expect_equal(step, "Lookup deleted applicant HTTP status", status, 404)
        expect_equal(step, "Lookup deleted applicant message", payload["message"], "Applicant not found.")

    return run_test_suite(
        "Applicant Smoke Test",
        f"{applicant_base}/applicant",
        [
            ("GET /applicant", test_get_all_applicants),
            ("GET /applicant/<applicant_id>", test_get_one_applicant),
            ("GET /applicant/nric/<nric>", test_get_applicant_by_nric),
            ("POST/PUT/DELETE /applicant", test_create_update_delete_applicant),
        ],
    )
