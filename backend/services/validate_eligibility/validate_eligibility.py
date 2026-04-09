"""
ValidateEligibility service.

Re-validates a BTO applicant's personal eligibility before balloting using
live Singpass/MyInfo data. Does NOT re-check HFE documents — those were
validated at application time and remain authoritative.

Checks performed (via Singpass profile):
  1. Citizenship      — main applicant must be SC; co-applicant SC or PR
  2. Marital status   — if co-applicant present, main applicant must still be married
  3. Private property — neither applicant may own private property
  4. HDB ownership    — neither applicant may currently own an HDB flat
  5. Income ceiling   — combined household income (from NOA) within flat-type ceiling

Expected request formats:
  GET /validate-eligibility?application_id=2001&main_applicant_nric=S9812381D
  POST /validate-eligibility/bulk with grouped application payloads
"""

import os
import re

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SINGPASS_SERVICE_URL = os.environ.get("SINGPASS_SERVICE_URL", "http://localhost:5007")
APPLICATION_SERVICE_URL = os.environ.get("APPLICATION_SERVICE_URL", "http://localhost:5004")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "15"))

# HDB household income ceilings (SGD/month) by flat type.
INCOME_CEILING_BY_FLAT_TYPE = {
    "2-Room Flexi": 7_000,
    "3-Room":       7_000,
    "4-Room":      14_000,
    "5-Room":      14_000,
    "Executive":   14_000,
    "3Gen":        21_000,
}

# Singpass residentialstatus codes
SC_CODE = "C"   # Singapore Citizen
PR_CODE = "P"   # Permanent Resident

# Singpass marital codes
MARRIED_CODE = "2"

app = Flask(__name__)
CORS(app)

app.config["SWAGGER"] = {
    "title": "Validate Eligibility API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": (
        "Re-validates BTO applicant personal eligibility before balloting using live "
        "Singpass/MyInfo data. Checks citizenship, marital status, private property "
        "ownership, HDB ownership, and income ceiling."
    ),
}
swagger = Swagger(app)


# ---------------------------------------------------------------------------
# Singpass helper
# ---------------------------------------------------------------------------

# Fetches one Singpass profile for the provided NRIC.
def fetch_singpass_profile(nric):
    """
    Fetch the MyInfo profile for the given NRIC from the Singpass service.
    Returns the profile dict, or None if not found.
    """
    response = requests.get(
        f"{SINGPASS_SERVICE_URL}/singpass/profile",
        params={"nric": nric},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


# Handles mark application ineligible.
def mark_application_ineligible(application_id):
    """
    Mark one application as ineligible in the application service.
    Returns a structured result for orchestration visibility.
    """
    try:
        response = requests.put(
            f"{APPLICATION_SERVICE_URL}/applications/{application_id}/eligibility",
            json={"eligible": False},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {
            "attempted": True,
            "updated": False,
            "status_code": None,
            "message": f"Failed to reach application service: {exc}",
        }

    message = "Application marked as UNSUCCESSFUL."
    payload = {}
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code != 200:
        upstream_message = payload.get("message") or payload.get("error")
        if isinstance(upstream_message, str) and upstream_message.strip():
            message = upstream_message
        else:
            message = f"Application service returned HTTP {response.status_code}."
        return {
            "attempted": True,
            "updated": False,
            "status_code": response.status_code,
            "message": message,
        }

    return {
        "attempted": True,
        "updated": True,
        "status_code": response.status_code,
        "message": message,
    }


# Fetches application record.
def fetch_application_record(application_id):
    """
    Fetch one application from application service.
    Returns (status_code, payload) where payload is dict on success or error payload.
    """
    try:
        response = requests.get(
            f"{APPLICATION_SERVICE_URL}/applications/{application_id}",
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return 502, {"error": f"Failed to reach application service: {exc}"}

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return response.status_code, payload


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

# Normalizes NRIC/FIN input for consistent matching.
def normalise_nric(value):
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


# Gets member by role.
def get_member_by_role(members, role):
    return next((m for m in (members or []) if m.get("member_role") == role), None)


# Builds check.
def make_check(name, passed, message):
    return {"check": name, "passed": passed, "blocking": True, "message": message}


# Parses numeric values from MyInfo wrappers/strings.
def parse_profile_number(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, dict):
        for key in ("value", "amount", "$numberDecimal", "$numberDouble", "$numberInt"):
            if key in value:
                parsed = parse_profile_number(value.get(key))
                if parsed is not None:
                    return parsed
        return None

    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    return None


# Gets monthly income from noa.
def get_monthly_income_from_noa(profile):
    """
    Extract monthly income from profile.

    Priority:
      1) explicit monthlyincome fields
      2) NOA annual amount/employment divided by 12
      3) annualincome fields divided by 12
      4) explicit zero monthlyincome (returns 0.0)
    """
    profile = profile or {}
    if not isinstance(profile, dict):
        return None

    monthly_candidates = (
        profile.get("monthlyincome"),
        profile.get("average_monthly_income"),
        profile.get("monthly_income"),
        profile.get("monthlyIncome"),
    )
    for candidate in monthly_candidates:
        parsed = parse_profile_number(candidate)
        if parsed is not None and parsed > 0:
            return parsed

    noa = profile.get("noa")
    if isinstance(noa, dict):
        annual_candidates = (noa.get("amount"), noa.get("employment"))
        for candidate in annual_candidates:
            parsed = parse_profile_number(candidate)
            if parsed is not None and parsed > 0:
                return parsed / 12

    annual_candidates = (
        profile.get("annualincome"),
        profile.get("annual_income"),
        profile.get("annualIncome"),
    )
    for candidate in annual_candidates:
        parsed = parse_profile_number(candidate)
        if parsed is not None and parsed > 0:
            return parsed / 12

    for candidate in monthly_candidates:
        parsed = parse_profile_number(candidate)
        if parsed is not None:
            return parsed

    return None


# ---------------------------------------------------------------------------
# Check 1 — Citizenship
# ---------------------------------------------------------------------------

# Runs citizenship checks for main and co-applicants.
def run_citizenship_checks(main_profile, co_profile, has_co_applicant):
    checks = []

    if main_profile is None:
        checks.append(make_check(
            "main_applicant_is_sc",
            False,
            "Could not retrieve Singpass profile for the main applicant.",
        ))
    else:
        code = (main_profile.get("residentialstatus") or {}).get("code", "")
        is_sc = code == SC_CODE
        checks.append(make_check(
            "main_applicant_is_sc",
            is_sc,
            "Main applicant is a Singapore Citizen." if is_sc
            else f"Main applicant residential status is '{code}'. Only Singapore Citizens may be the main applicant.",
        ))

    if has_co_applicant:
        if co_profile is None:
            checks.append(make_check(
                "co_applicant_is_sc_or_pr",
                False,
                "Could not retrieve Singpass profile for the co-applicant.",
            ))
        else:
            code = (co_profile.get("residentialstatus") or {}).get("code", "")
            is_eligible = code in {SC_CODE, PR_CODE}
            label = "a Singapore Citizen" if code == SC_CODE else "a Permanent Resident"
            checks.append(make_check(
                "co_applicant_is_sc_or_pr",
                is_eligible,
                f"Co-applicant is {label}." if is_eligible
                else f"Co-applicant residential status is '{code}'. Co-applicants must be SC or PR.",
            ))

    return checks


# ---------------------------------------------------------------------------
# Check 2 — Marital status
# ---------------------------------------------------------------------------

# Verifies marital status when a co-applicant is present.
def run_marital_checks(main_profile, has_co_applicant):
    """
    If a co-applicant is present (family nucleus scheme), the main applicant
    must still be married. Singles applying alone for 2-Room Flexi are exempt.
    """
    checks = []

    if not has_co_applicant:
        checks.append(make_check(
            "marital_status_valid",
            True,
            "Single applicant — marital status check not applicable.",
        ))
        return checks

    if main_profile is None:
        checks.append(make_check(
            "marital_status_valid",
            False,
            "Could not retrieve Singpass profile to verify marital status.",
        ))
        return checks

    marital = main_profile.get("marital") or {}
    code = marital.get("code", "")
    desc = marital.get("desc", code)
    is_married = code == MARRIED_CODE
    checks.append(make_check(
        "marital_status_valid",
        is_married,
        "Main applicant is married — family nucleus is intact." if is_married
        else f"Main applicant marital status is '{desc}'. A valid family nucleus is required when a co-applicant is present.",
    ))

    return checks


# ---------------------------------------------------------------------------
# Check 3 — Private property ownership
# ---------------------------------------------------------------------------

# Checks whether applicants currently own private property.
def run_private_property_checks(main_profile, co_profile, has_co_applicant):
    checks = []

    profiles = [("main applicant", "main_applicant_no_private_property", main_profile)]
    if has_co_applicant:
        profiles.append(("co-applicant", "co_applicant_no_private_property", co_profile))

    for label, check_name, profile in profiles:
        if profile is None:
            checks.append(make_check(
                check_name,
                False,
                f"Could not retrieve Singpass profile for {label} to verify private property ownership.",
            ))
            continue

        owns_private = (profile.get("ownerprivate") or {}).get("value", False)
        checks.append(make_check(
            check_name,
            not owns_private,
            f"The {label} does not own any private property." if not owns_private
            else f"The {label} currently owns private property and is not eligible to apply for a BTO.",
        ))

    return checks


# ---------------------------------------------------------------------------
# Check 4 — HDB ownership
# ---------------------------------------------------------------------------

# Checks whether applicants currently own an HDB flat.
def run_hdb_ownership_checks(main_profile, co_profile, has_co_applicant):
    checks = []

    profiles = [("main applicant", "main_applicant_no_hdb", main_profile)]
    if has_co_applicant:
        profiles.append(("co-applicant", "co_applicant_no_hdb", co_profile))

    for label, check_name, profile in profiles:
        if profile is None:
            checks.append(make_check(
                check_name,
                False,
                f"Could not retrieve Singpass profile for {label} to verify HDB ownership.",
            ))
            continue

        hdb_ownership = profile.get("hdbownership") or []
        owns_hdb = isinstance(hdb_ownership, list) and len(hdb_ownership) > 0
        checks.append(make_check(
            check_name,
            not owns_hdb,
            f"The {label} does not own an HDB flat." if not owns_hdb
            else f"The {label} currently owns an HDB flat and is not eligible to apply for a new BTO.",
        ))

    return checks


# ---------------------------------------------------------------------------
# Check 5 — Income ceiling
# ---------------------------------------------------------------------------

# Validates that household income stays within the flat-type ceiling.
def run_income_checks(main_profile, co_profile, has_co_applicant, flat_type):
    checks = []

    ceiling = INCOME_CEILING_BY_FLAT_TYPE.get(flat_type)
    if ceiling is None:
        checks.append(make_check(
            "income_within_ceiling",
            False,
            f"No income ceiling defined for flat type '{flat_type}'.",
        ))
        return checks

    main_monthly = get_monthly_income_from_noa(main_profile)
    if main_monthly is None:
        checks.append(make_check(
            "income_within_ceiling",
            False,
            "Could not retrieve income (NOA) for main applicant from Singpass.",
        ))
        return checks

    co_monthly = 0.0
    if has_co_applicant and co_profile is not None:
        co_monthly = get_monthly_income_from_noa(co_profile) or 0.0

    household_monthly = main_monthly + co_monthly
    within = household_monthly <= ceiling

    checks.append(make_check(
        "income_within_ceiling",
        within,
        f"Combined household income (${household_monthly:,.2f}/month) is within the "
        f"${ceiling:,}/month ceiling for {flat_type}." if within
        else f"Combined household income (${household_monthly:,.2f}/month) exceeds the "
             f"${ceiling:,}/month ceiling for {flat_type}.",
    ))

    return checks


# ---------------------------------------------------------------------------
# Validation core
# ---------------------------------------------------------------------------

def validate_application_payload(application_id, provided_main_nric=None, provided_co_nric=None):
    """Validate one application and return a structured orchestration-friendly payload."""
    app_status, application_record = fetch_application_record(application_id)
    if app_status == 404:
        return 404, {
            "error": f"Application {application_id} not found.",
            "application_id": application_id,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": 404,
                "message": "Application record not found.",
            },
        }
    if app_status != 200:
        return 502, {
            "error": application_record.get("error") or "Unable to fetch application record.",
            "application_id": application_id,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": app_status,
                "message": "Unable to fetch application record.",
            },
        }

    main_nric = normalise_nric(application_record.get("main_applicant_nric"))
    flat_type = (application_record.get("flat_type") or "").strip()
    members = application_record.get("members") or []

    if main_nric is None:
        return 400, {
            "error": "Application record is missing main_applicant_nric.",
            "application_id": application_id,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": 400,
                "message": "Application record is missing main_applicant_nric.",
            },
        }

    if provided_main_nric and provided_main_nric != main_nric:
        return 400, {
            "error": "main_applicant_nric does not match the application record.",
            "application_id": application_id,
            "main_applicant_nric": main_nric,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": 400,
                "message": "main_applicant_nric does not match the application record.",
            },
        }

    co_member = get_member_by_role(members, "CO_APPLICANT")
    has_co_applicant = co_member is not None
    co_nric = normalise_nric(co_member.get("nric_fin")) if co_member else None

    if provided_co_nric and provided_co_nric != co_nric:
        return 400, {
            "error": "co_applicant_nric does not match the application record.",
            "application_id": application_id,
            "co_applicant_nric": co_nric,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": 400,
                "message": "co_applicant_nric does not match the application record.",
            },
        }

    try:
        main_profile = fetch_singpass_profile(main_nric)
        co_profile = fetch_singpass_profile(co_nric) if co_nric else None
    except requests.RequestException as exc:
        return 502, {
            "error": f"Failed to reach Singpass service: {exc}",
            "application_id": application_id,
            "main_applicant_nric": main_nric,
            "co_applicant_nric": co_nric,
            "application_update": {
                "attempted": False,
                "updated": False,
                "status_code": 502,
                "message": f"Failed to reach Singpass service: {exc}",
            },
        }

    all_checks = {
        "citizenship": run_citizenship_checks(main_profile, co_profile, has_co_applicant),
        "marital_status": run_marital_checks(main_profile, has_co_applicant),
        "private_property": run_private_property_checks(main_profile, co_profile, has_co_applicant),
        "hdb_ownership": run_hdb_ownership_checks(main_profile, co_profile, has_co_applicant),
        "income_ceiling": run_income_checks(main_profile, co_profile, has_co_applicant, flat_type),
    }

    ineligibility_reasons = list(dict.fromkeys(
        check["message"]
        for category in all_checks.values()
        for check in category
        if not check["passed"]
    ))

    eligible = len(ineligibility_reasons) == 0
    application_update = {
        "attempted": False,
        "updated": False,
        "status_code": None,
        "message": "No application status update required.",
    }
    if not eligible:
        application_update = mark_application_ineligible(application_id)

    return 200, {
        "application_id": application_id,
        "main_applicant_nric": main_nric,
        "co_applicant_nric": co_nric,
        "flat_type": flat_type,
        "eligible": eligible,
        "checks": all_checks,
        "ineligibility_reasons": ineligibility_reasons,
        "application_update": application_update,
    }


# ---------------------------------------------------------------------------
# Main endpoints
# ---------------------------------------------------------------------------

# Handles the eligibility re-validation flow before balloting.
@app.route("/validate-eligibility", methods=["GET"])
def validate_eligibility():
    """
    Re-validate personal eligibility before balloting
    ---
    tags:
      - Validate Eligibility
    summary: Validate applicant eligibility via Singpass
    description: |
      Fetches live Singpass/MyInfo data for the main applicant (and co-applicant
      if present) and runs five personal eligibility checks: citizenship, marital
      status, private property ownership, HDB ownership, and income ceiling.
      Does not re-check HFE documents.
    parameters:
      - in: query
        name: application_id
        required: true
        schema:
          type: integer
      - in: query
        name: main_applicant_nric
        required: false
        schema:
          type: string
      - in: query
        name: co_applicant_nric
        required: false
        schema:
          type: string
    responses:
      200:
        description: Validation completed (see eligible field for result)
      400:
        description: Missing or invalid fields in the request
      502:
        description: Failed to reach the Singpass service
    """
    application_id_raw = request.args.get("application_id")
    if not isinstance(application_id_raw, str) or not application_id_raw.isdigit():
        return jsonify({"error": "application_id is required and must be a positive integer."}), 400

    application_id = int(application_id_raw)
    if application_id <= 0:
        return jsonify({"error": "application_id is required and must be a positive integer."}), 400

    provided_main_nric = normalise_nric(request.args.get("main_applicant_nric"))
    provided_co_nric = normalise_nric(request.args.get("co_applicant_nric"))
    status_code, payload = validate_application_payload(
        application_id,
        provided_main_nric=provided_main_nric,
        provided_co_nric=provided_co_nric,
    )
    return jsonify(payload), status_code


@app.route("/validate-eligibility/bulk", methods=["POST"])
def validate_eligibility_bulk():
    """Validate multiple applications in grouped batches."""
    payload = request.get_json(silent=True) or {}
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        return jsonify({"error": "groups must be a non-empty list."}), 400

    grouped_results = []
    warnings = []

    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            warnings.append(f"Skipped non-object group at index {group_index}.")
            continue

        town_name = group.get("town_name")
        flat_type = group.get("flat_type")
        rows = group.get("applications")
        if not isinstance(rows, list) or not rows:
            warnings.append(f"Skipped invalid or empty applications list in group index {group_index}.")
            continue

        group_results = []
        group_warnings = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                group_warnings.append(f"Skipped non-object item at index {row_index}.")
                continue

            application_id = row.get("application_id")
            if not isinstance(application_id, int) or application_id <= 0:
                group_results.append({
                    "application_id": application_id,
                    "eligible": False,
                    "ineligibility_reasons": ["application_id is required and must be a positive integer."],
                    "application_update": {
                        "attempted": False,
                        "updated": False,
                        "status_code": 400,
                        "message": "Validation skipped due to invalid application_id.",
                    },
                    "validation_status_code": 400,
                })
                continue

            status_code, result = validate_application_payload(
                application_id,
                provided_main_nric=normalise_nric(row.get("main_applicant_nric")),
                provided_co_nric=normalise_nric(row.get("co_applicant_nric")),
            )
            result["validation_status_code"] = status_code
            group_results.append(result)

        grouped_results.append({
            "town_name": town_name if isinstance(town_name, str) else None,
            "flat_type": flat_type if isinstance(flat_type, str) else None,
            "count": len(group_results),
            "warnings": group_warnings,
            "results": group_results,
        })

    return jsonify({
        "count": sum(group.get("count", 0) for group in grouped_results if isinstance(group, dict)),
        "warnings": warnings,
        "groups": grouped_results,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5013, debug=False)
