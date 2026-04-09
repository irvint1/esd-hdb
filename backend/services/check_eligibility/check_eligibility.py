"""
CheckEligibility service.

Orchestrates eligibility validation for a BTO application by:
  1. Uploading the income and HFE documents to the Document Service for OCR extraction
  2. Looking up the authoritative HFE application record from the HFE Application Service
     (using the NRIC extracted from the HFE document to confirm it belongs to this applicant)
  3. Running five categories of checks
  4. Returning a structured result indicating eligibility, plus the new document IDs so the
     caller can store them on the application record

Expected request format  (multipart/form-data)
----------------------------------------------
  application      JSON string, e.g.:
                     {
                       "application_id":      2001,
                       "main_applicant_nric": "S9812381D",
                       "flat_type":           "4-Room",
                       "members": [
                         { "member_role": "MAIN_APPLICANT", "nric_fin": "S9812381D", "full_name": "TAN HENG HUAT" },
                         { "member_role": "CO_APPLICANT",   "nric_fin": "S9812382B", "full_name": "FREYA LIM GUO EN" }
                       ]
                     }
  income_document  PDF file (income statement / CPF contribution history)
  hfe_document     PDF file (HFE letter)
"""

import os
from datetime import date

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger
import json


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DOCUMENT_SERVICE_URL       = os.environ.get("DOCUMENT_SERVICE_URL",       "http://localhost:5050")
HFE_APPLICATION_SERVICE_URL = os.environ.get("HFE_APPLICATION_SERVICE_URL", "http://localhost:5009")
REQUEST_TIMEOUT             = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "15"))

# HDB household income ceilings (SGD/month) by flat type.
# Source: HDB eligibility conditions for BTO flats.
INCOME_CEILING_BY_FLAT_TYPE = {
    "2-Room Flexi": 7_000,
    "3-Room":       7_000,
    "4-Room":      14_000,
    "5-Room":      14_000,
    "Executive":   14_000,
    "3Gen":        21_000,
}

# If extracted income differs from HFE-declared income by more than this fraction,
# it may indicate an outdated or incorrect HFE declaration.
INCOME_DISCREPANCY_THRESHOLD = 0.20  # 20 %

app = Flask(__name__)
CORS(app)

app.config["SWAGGER"] = {
    "title": "Check Eligibility API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": (
        "Validates BTO applications against HFE application records and uploaded documents. "
        "Runs five check categories: HFE validation, income validation, household consistency, "
        "flat eligibility, and document validation."
    ),
}
swagger = Swagger(app)


# ---------------------------------------------------------------------------
# HTTP helpers calls to upstream services
# ---------------------------------------------------------------------------

#  Handles extract document for this service.
def extract_document(file_storage, application_id):
    """
    Upload a PDF file to the Document Service for OCR extraction.

    The Document Service auto-detects whether the file is an income document or
    an HFE letter, extracts structured fields, and persists the record.

    Returns the full response dict, e.g.:
      { "document_id": 7, "document_type": "income", "status": "processed", "fields": { ... } }
    """
    response = requests.post(
        f"{DOCUMENT_SERVICE_URL}/extract",
        files={"file": (file_storage.filename, file_storage.read(), file_storage.content_type)},
        data={"application_id": application_id},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


#  Handles fetch hfe application for this service.
def fetch_hfe_application(main_applicant_nric):
    """
    Fetch the authoritative HFE application record for the given NRIC from the
    HFE Application Service.  Returns the record dict, or None if not found.
    """
    response = requests.get(
        f"{HFE_APPLICATION_SERVICE_URL}/hfe-applications",
        params={"main_applicant_nric": main_applicant_nric},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Small utility functions
# ---------------------------------------------------------------------------

#  Handles normalise nric for this service.
def normalise_nric(value):
    """Return an uppercase, stripped NRIC string, or None if the input is invalid."""
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


#  Handles parse iso date for this service.
def parse_iso_date(value):
    """Parse an ISO-8601 date string (YYYY-MM-DD) into a date object, or None."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


#  Handles split flat types for this service.
def split_flat_types(eligible_flat_types_str):
    """
    Convert the comma-separated eligible_flat_types string stored in the HFE
    record into a set, e.g. '3-Room, 4-Room' -> {'3-Room', '4-Room'}.
    """
    if not isinstance(eligible_flat_types_str, str):
        return set()
    return {ft.strip() for ft in eligible_flat_types_str.split(",") if ft.strip()}


#  Handles get member by role for this service.
def get_member_by_role(members, role):
    """Return the first member dict whose member_role matches the given role, or None."""
    return next((m for m in (members or []) if m.get("member_role") == role), None)


# ---------------------------------------------------------------------------
# Check builder
# ---------------------------------------------------------------------------

#  Handles make check for this service.
def make_check(name, passed, message):
    """
    Build a single check result dict.

    name     machine-readable identifier for the check
    passed   True / False
    message  human-readable description of what was checked and the outcome
    Every check is treated as blocking when it fails.
    """
    return {
        "check":    name,
        "passed":   passed,
        "blocking": True,
        "message":  message,
    }


# ---------------------------------------------------------------------------
# Check category 1 HFE Validation
# ---------------------------------------------------------------------------

#  Handles run hfe checks for this service.
def run_hfe_checks(application, hfe_record):
    """
    Validate the HFE application record:
      - Record exists for this NRIC
      - Assessment outcome is ELIGIBLE
      - HFE has not expired
      - NRIC on HFE matches the applicant
      - Co-applicant on HFE matches the application
    """
    checks = []

    if hfe_record is None:
        checks.append(make_check(
            "hfe_record_exists", False,
            "No HFE application record was found for this applicant's NRIC. "
            "The applicant must hold a valid HFE letter before applying."
        ))
        # All subsequent HFE checks are meaningless without the record.
        return checks

    checks.append(make_check("hfe_record_exists", True, "HFE application record found."))

    # --- Assessment outcome ---
    outcome = (hfe_record.get("assessment_outcome") or "").upper()
    hfe_approved = "ELIGIBLE" in outcome
    checks.append(make_check(
        "hfe_is_approved",
        hfe_approved,
        f"HFE assessment outcome is '{outcome}' (ELIGIBLE)." if hfe_approved
        else f"HFE assessment outcome is '{outcome}'. Only ELIGIBLE applicants may proceed.",
    ))

    # --- Expiry ---
    valid_until = parse_iso_date(hfe_record.get("valid_until"))
    if valid_until is None:
        checks.append(make_check(
            "hfe_not_expired", False,
            "HFE valid_until date is missing cannot confirm the letter is still valid.",
        ))
    else:
        hfe_still_valid = valid_until >= date.today()
        checks.append(make_check(
            "hfe_not_expired",
            hfe_still_valid,
            f"HFE letter is valid until {valid_until}." if hfe_still_valid
            else f"HFE letter expired on {valid_until}. A renewed HFE letter is required.",
        ))

    # --- Applicant NRIC ---
    application_nric = normalise_nric(application.get("main_applicant_nric"))
    hfe_nric         = normalise_nric(hfe_record.get("main_applicant_nric"))
    nric_matches     = application_nric == hfe_nric
    checks.append(make_check(
        "applicant_nric_matches_hfe",
        nric_matches,
        f"Applicant NRIC ({application_nric}) matches the HFE record." if nric_matches
        else f"Applicant NRIC ({application_nric}) does not match the NRIC on the HFE record ({hfe_nric}).",
    ))

    # --- Co-applicant ---
    co_member     = get_member_by_role(application.get("members"), "CO_APPLICANT")
    hfe_co_nric   = normalise_nric(hfe_record.get("co_applicant_nric"))
    app_co_nric   = normalise_nric(co_member.get("nric_fin")) if co_member else None

    if app_co_nric and hfe_co_nric:
        co_matches = app_co_nric == hfe_co_nric
        checks.append(make_check(
            "co_applicant_matches_hfe",
            co_matches,
            f"Co-applicant NRIC ({app_co_nric}) matches the HFE record." if co_matches
            else f"Co-applicant NRIC ({app_co_nric}) does not match the HFE co-applicant ({hfe_co_nric}).",
        ))
    elif not app_co_nric and not hfe_co_nric:
        checks.append(make_check(
            "co_applicant_matches_hfe", True,
            "No co-applicant in the application or HFE record consistent.",
        ))
    else:
        checks.append(make_check(
            "co_applicant_matches_hfe", False,
            "Co-applicant is present in the application but not the HFE record, or vice versa.",
        ))

    return checks


# ---------------------------------------------------------------------------
# Check category 2 Income Validation
# ---------------------------------------------------------------------------

#  Handles run income checks for this service.
def run_income_checks(application, income_fields, hfe_record):
    """
    Validate the income document against the HFE declaration:
      - Income document belongs to the applicant or co-applicant
      - Extracted income is within 20 % of HFE-declared household income
      - Household income is within the eligibility ceiling for the selected flat type
    """
    checks = []

    application_nric = normalise_nric(application.get("main_applicant_nric"))
    co_member        = get_member_by_role(application.get("members"), "CO_APPLICANT")
    co_nric          = normalise_nric(co_member.get("nric_fin")) if co_member else None
    income_nric      = normalise_nric(income_fields.get("main_applicant_nric"))

    # --- Ownership ---
    income_belongs = income_nric in {application_nric, co_nric}
    checks.append(make_check(
        "income_doc_belongs_to_applicant",
        income_belongs,
        f"Income document NRIC ({income_nric}) matches the applicant or co-applicant." if income_belongs
        else f"Income document NRIC ({income_nric}) does not match the applicant ({application_nric}) "
             f"or co-applicant ({co_nric}).",
    ))

    # --- Income consistency with HFE ---
    # Use combined income for joint statements, otherwise single applicant income.
    extracted_monthly_income = (
        income_fields.get("combined_average_monthly_income")
        or income_fields.get("average_monthly_income")
    )
    hfe_declared_income = hfe_record.get("total_household_income") if hfe_record else None

    if extracted_monthly_income is None or hfe_declared_income is None:
        checks.append(make_check(
            "income_consistent_with_hfe", False,
            "Cannot compare income figures: one or both values are missing from the documents.",
        ))
    else:
        extracted = float(extracted_monthly_income)
        declared  = float(hfe_declared_income)

        if declared == 0:
            consistent = extracted == 0
        else:
            discrepancy_pct = abs(extracted - declared) / declared
            consistent = discrepancy_pct <= INCOME_DISCREPANCY_THRESHOLD

        checks.append(make_check(
            "income_consistent_with_hfe",
            consistent,
            f"Extracted monthly income (${extracted:,.2f}) is consistent with "
            f"HFE-declared income (${declared:,.2f})." if consistent
            else f"Extracted monthly income (${extracted:,.2f}) differs from HFE-declared "
                 f"income (${declared:,.2f}) by more than {int(INCOME_DISCREPANCY_THRESHOLD * 100)} %. "
                 "This may indicate an outdated or incorrect HFE declaration.",
        ))

    # --- Income ceiling ---
    flat_type     = (application.get("flat_type") or "").strip()
    ceiling       = INCOME_CEILING_BY_FLAT_TYPE.get(flat_type)
    income_figure = float(hfe_declared_income) if hfe_declared_income is not None else None

    if ceiling is None:
        checks.append(make_check(
            "income_within_ceiling", False,
            f"No income ceiling is defined for flat type '{flat_type}'.",
        ))
    elif income_figure is None:
        checks.append(make_check(
            "income_within_ceiling", False,
            "Cannot check income ceiling: HFE-declared income figure is unavailable.",
        ))
    else:
        within_ceiling = income_figure <= ceiling
        checks.append(make_check(
            "income_within_ceiling",
            within_ceiling,
            f"Household income (${income_figure:,.2f}/month) is within the "
            f"${ceiling:,}/month ceiling for {flat_type}." if within_ceiling
            else f"Household income (${income_figure:,.2f}/month) exceeds the "
                 f"${ceiling:,}/month ceiling for {flat_type}.",
        ))

    return checks


# ---------------------------------------------------------------------------
# Check category 3 Household Consistency
# ---------------------------------------------------------------------------

#  Handles run household checks for this service.
def run_household_checks(application, hfe_record):
    """
    Verify that the household composition in the application matches the HFE record:
      - Main applicant name matches
      - Co-applicant name matches (or both absent)
    """
    checks = []

    if hfe_record is None:
        checks.append(make_check(
            "household_matches_hfe", False,
            "Cannot verify household consistency: HFE record is not available.",
        ))
        return checks

    # --- Main applicant name ---
    main_member    = get_member_by_role(application.get("members"), "MAIN_APPLICANT")
    app_main_name  = (main_member.get("full_name") or "").strip().upper() if main_member else ""
    hfe_main_name  = (hfe_record.get("main_applicant_name") or "").strip().upper()
    main_name_ok   = app_main_name == hfe_main_name
    checks.append(make_check(
        "main_applicant_name_matches_hfe",
        main_name_ok,
        f"Main applicant name '{app_main_name}' matches the HFE record." if main_name_ok
        else f"Main applicant name '{app_main_name}' does not match "
             f"the HFE record name '{hfe_main_name}'.",
    ))

    # --- Co-applicant name ---
    co_member     = get_member_by_role(application.get("members"), "CO_APPLICANT")
    app_co_name   = (co_member.get("full_name") or "").strip().upper() if co_member else None
    hfe_co_name   = (hfe_record.get("co_applicant_name") or "").strip().upper() \
                    if hfe_record.get("co_applicant_name") else None

    if app_co_name and hfe_co_name:
        co_name_ok = app_co_name == hfe_co_name
        checks.append(make_check(
            "co_applicant_name_matches_hfe",
            co_name_ok,
            f"Co-applicant name '{app_co_name}' matches the HFE record." if co_name_ok
            else f"Co-applicant name '{app_co_name}' does not match "
                 f"the HFE record name '{hfe_co_name}'.",
        ))
    elif not app_co_name and not hfe_co_name:
        checks.append(make_check(
            "co_applicant_name_matches_hfe", True,
            "No co-applicant in the application or HFE record consistent.",
        ))
    else:
        checks.append(make_check(
            "co_applicant_name_matches_hfe", False,
            "Co-applicant is present in the application but absent from the HFE record, "
            "or vice versa.",
        ))

    return checks


# ---------------------------------------------------------------------------
# Check category 4 Flat Eligibility
# ---------------------------------------------------------------------------

#  Handles run flat eligibility checks for this service.
def run_flat_eligibility_checks(application, hfe_record):
    """
    Confirm the selected flat type is appropriate:
      - A flat type has been selected
      - Household size is sufficient for the selected flat type
      - 3/4/5-Room applications include at least 2 household members
      - Flat type aligns with the HFE-approved eligible flat types
    """
    checks = []

    selected_flat   = (application.get("flat_type") or "").strip()
    members         = application.get("members") or []
    household_size  = len(members)
    co_member       = get_member_by_role(members, "CO_APPLICANT")

    # --- Flat type selected ---
    if not selected_flat:
        checks.append(make_check("flat_type_selected", False, "No flat type has been selected."))
        return checks

    checks.append(make_check("flat_type_selected", True, f"Flat type '{selected_flat}' is selected."))

    # --- Household size ---
    min_size  = 1 if "2-Room" in selected_flat else 2
    size_ok   = household_size >= min_size
    checks.append(make_check(
        "household_size_supports_flat",
        size_ok,
        f"Household size ({household_size}) meets the minimum of {min_size} for a {selected_flat}."
        if size_ok else
        f"Household size ({household_size}) is below the minimum of {min_size} required for a {selected_flat}.",
    ))

    # --- 2-Room singles are allowed ---
    if "2-Room" in selected_flat:
        checks.append(make_check(
            "two_room_single_applicant_allowed",
            True,
            "2-Room applications may be submitted without a co-applicant.",
        ))

    # --- HFE-approved flat types ---
    if hfe_record:
        allowed_flat_types = split_flat_types(hfe_record.get("eligible_flat_types"))
        flat_aligns = selected_flat in allowed_flat_types
        checks.append(make_check(
            "flat_type_aligns_with_hfe",
            flat_aligns,
            f"'{selected_flat}' is in the HFE-approved list "
            f"({', '.join(sorted(allowed_flat_types))})." if flat_aligns
            else f"'{selected_flat}' is not in the HFE-approved list "
                 f"({', '.join(sorted(allowed_flat_types))}).",
        ))

    return checks


# ---------------------------------------------------------------------------
# Check category 5 Document Validation
# ---------------------------------------------------------------------------

#  Handles run document checks for this service.
def run_document_checks(application, income_doc, hfe_doc, income_fields, hfe_fields):
    """
    Confirm that both documents were successfully extracted, contain fields,
    and belong to the correct applicants.
    """
    checks = []

    application_nric = normalise_nric(application.get("main_applicant_nric"))

    # --- Income document extraction ---
    if income_doc:
        income_processed = income_doc.get("status") == "processed"
        checks.append(make_check(
            "income_document_extracted",
            income_processed,
            "Income document was successfully extracted." if income_processed
            else f"Income document extraction failed (status: '{income_doc.get('status')}').",
        ))
        checks.append(make_check(
            "income_document_has_fields",
            bool(income_fields),
            "Income document contains extracted fields." if income_fields
            else "Income document has no extracted fields the PDF may be unreadable.",
        ))

    # --- HFE document extraction ---
    if hfe_doc:
        hfe_processed = hfe_doc.get("status") == "processed"
        checks.append(make_check(
            "hfe_document_extracted",
            hfe_processed,
            "HFE document was successfully extracted." if hfe_processed
            else f"HFE document extraction failed (status: '{hfe_doc.get('status')}').",
        ))
        checks.append(make_check(
            "hfe_document_has_fields",
            bool(hfe_fields),
            "HFE document contains extracted fields." if hfe_fields
            else "HFE document has no extracted fields the PDF may be unreadable.",
        ))

    # --- NRIC ownership checks ---
    if hfe_fields:
        hfe_doc_nric  = normalise_nric(hfe_fields.get("main_applicant_nric"))
        hfe_doc_owned = hfe_doc_nric == application_nric
        checks.append(make_check(
            "hfe_doc_nric_matches_applicant",
            hfe_doc_owned,
            f"HFE document NRIC ({hfe_doc_nric}) matches the applicant." if hfe_doc_owned
            else f"HFE document NRIC ({hfe_doc_nric}) does not match the applicant ({application_nric}).",
        ))

    return checks


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

#  Handles check eligibility for this service.
@app.route("/check-eligibility", methods=["POST"])
def check_eligibility():
    """
    Run all eligibility checks for a BTO application
    ---
    tags:
      - Eligibility
    summary: Check BTO application eligibility
    description: |
      Accepts the application details and two PDF files (income document and HFE letter)
      as multipart/form-data. Uploads both files to the Document Service for OCR extraction,
      retrieves the authoritative HFE application record, then runs five categories of
      eligibility checks. Returns eligible: true only when all blocking checks pass.
      The response includes the new document IDs so the caller can store them on the application.
    consumes:
      - multipart/form-data
    requestBody:
      required: true
      content:
        multipart/form-data:
          schema:
            type: object
            required:
              - application
              - income_document
              - hfe_document
            properties:
              application:
                type: string
                description: >
                  JSON string containing application_id, main_applicant_nric,
                  flat_type, and members array.
              income_document:
                type: string
                format: binary
                description: Income statement or CPF contribution history PDF.
              hfe_document:
                type: string
                format: binary
                description: HFE letter PDF.
    responses:
      200:
        description: Eligibility check completed (see eligible field for result)
      400:
        description: Missing or invalid fields in the request
      502:
        description: Failed to reach an upstream service (Document or HFE Application)
    """

    # ------------------------------------------------------------------
    # Parse the application JSON from the form field
    # ------------------------------------------------------------------
    raw_application = request.form.get("application")
    if not raw_application:
        return jsonify({"error": "'application' form field is required."}), 400

    try:
        application = json.loads(raw_application)
    except (ValueError, TypeError):
        return jsonify({"error": "'application' must be a valid JSON string."}), 400

    if not isinstance(application, dict):
        return jsonify({"error": "'application' must be a JSON object."}), 400

    required_fields = ["application_id", "main_applicant_nric", "flat_type", "members"]
    missing = [f for f in required_fields if application.get(f) is None]
    if missing:
        return jsonify({
            "error": "Missing required application fields.",
            "details": [f"'{f}' is required." for f in missing],
        }), 400

    # ------------------------------------------------------------------
    # Validate that both PDF files are present
    # ------------------------------------------------------------------
    income_file = request.files.get("income_document")
    hfe_file    = request.files.get("hfe_document")

    if not income_file:
        return jsonify({"error": "'income_document' file is required."}), 400
    if not hfe_file:
        return jsonify({"error": "'hfe_document' file is required."}), 400

    # ------------------------------------------------------------------
    # Step 1 Upload both PDFs to the Document Service for OCR extraction
    # ------------------------------------------------------------------
    application_id = application["application_id"]

    try:
        income_doc = extract_document(income_file, application_id)
        hfe_doc    = extract_document(hfe_file,    application_id)
    except requests.RequestException as exc:
        return jsonify({"error": f"Failed to extract document via Document Service: {exc}"}), 502

    income_fields = income_doc.get("fields") or {}
    hfe_fields    = hfe_doc.get("fields") or {}

    # ------------------------------------------------------------------
    # Step 2 Fetch the HFE application record from the HFE Application Service
    #
    # We prefer the NRIC extracted from the HFE document itself (confirms the
    # document belongs to this applicant) and fall back to the application NRIC.
    # ------------------------------------------------------------------
    lookup_nric = normalise_nric(hfe_fields.get("main_applicant_nric")) \
               or normalise_nric(application.get("main_applicant_nric"))

    try:
        hfe_record = fetch_hfe_application(lookup_nric)
    except requests.RequestException as exc:
        return jsonify({"error": f"Failed to fetch HFE application record: {exc}"}), 502

    # ------------------------------------------------------------------
    # Step 3 Run all five check categories
    # ------------------------------------------------------------------
    all_checks = {
        "hfe_validation":        run_hfe_checks(application, hfe_record),
        "income_validation":     run_income_checks(application, income_fields, hfe_record),
        "household_consistency": run_household_checks(application, hfe_record),
        "flat_eligibility":      run_flat_eligibility_checks(application, hfe_record),
        "document_validation":   run_document_checks(
                                     application, income_doc, hfe_doc, income_fields, hfe_fields
                                 ),
    }

    # Collect every failed check message (all checks are blocking).
    raw_ineligibility_reasons = [
        check["message"]
        for category in all_checks.values()
        for check in category
        if not check["passed"]
    ]
    ineligibility_reasons = list(dict.fromkeys(raw_ineligibility_reasons))

    eligible = len(ineligibility_reasons) == 0

    return jsonify({
        "application_id":     application_id,
        "eligible":           eligible,
        "summary": (
            "Application passed all eligibility checks."
            if eligible else
            "Application failed one or more eligibility checks."
        ),
        "ineligibility_reasons": ineligibility_reasons,
        "checks":             all_checks,
        # Return the document IDs so Apply for BTO can store them on the application record.
        "income_document_id": income_doc.get("document_id"),
        "hfe_document_id":    hfe_doc.get("document_id"),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5008, debug=False)
