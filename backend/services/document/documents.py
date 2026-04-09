"""OCR service for income statements and HFE letters."""

import io
import hashlib
import os
import re
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    try:
        import fitz  # type: ignore[no-redef]
    except Exception:  # pragma: no cover - local environment fallback
        fitz = None  # type: ignore[assignment]

import pytesseract
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flasgger import Swagger
from flask_sqlalchemy import SQLAlchemy
from pdf2image import convert_from_bytes
from PIL import Image, ImageFilter

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional direct-text fallback
    PdfReader = None  # type: ignore[assignment]

app = Flask(__name__)
CORS(app)

app.config["SWAGGER"] = {
    "title": "OCR Service API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": "Extracts structured fields from income PDFs and HFE letters",
}
swagger = Swagger(app)

DATA_DIR = Path(os.environ.get("OCR_DATA_DIR", "/data"))
STORAGE_DIR = Path(os.environ.get("OCR_STORAGE_DIR", str(DATA_DIR / "documents")))
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+mysqlconnector://root:root@document-db:3306/documents",
)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 299}

db = SQLAlchemy(app)


class Document(db.Model):
    __tablename__ = "documents"

    document_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    application_id = db.Column(db.BigInteger, nullable=False)
    document_type = db.Column(db.String(20), nullable=False)
    storage_path = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    fields_json = db.Column(db.JSON, nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())

    # what this function does for the service: Handles to dict for this service.
    def to_dict(self):
        return {
            "document_id": self.document_id,
            "application_id": self.application_id,
            "document_type": self.document_type,
            "storage_path": self.storage_path,
            "status": self.status,
            "fields": self.fields_json,
            "uploaded_at": self.uploaded_at.isoformat(sep=" ") if self.uploaded_at else None,
        }


# what this function does for the service: Handles init storage for this service.
def init_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


# what this function does for the service: Handles get document record for this service.
def get_document_record(document_id):
    return db.session.get(Document, document_id)


# what this function does for the service: Handles get existing document for this service.
def get_existing_document(application_id, document_type):
    if not application_id:
        return None

    query = db.select(Document).where(
        Document.application_id == application_id,
        Document.document_type == document_type,
    )
    return db.session.scalar(query)


# what this function does for the service: Handles save document record for this service.
def save_document_record(
    application_id,
    document_type,
    storage_path,
    status,
    fields,
):
    existing = get_existing_document(application_id, document_type)
    if existing is None:
        existing = Document()
        db.session.add(existing)

    existing.application_id = application_id
    existing.document_type = document_type
    existing.storage_path = str(storage_path)
    existing.status = status
    existing.fields_json = fields
    db.session.commit()
    return existing


# what this function does for the service: Handles update document record for this service.
def update_document_record(document_id, document_type, status, fields):
    existing = get_document_record(document_id)
    if existing is None:
        return

    existing.document_type = document_type
    existing.status = status
    existing.fields_json = fields
    db.session.commit()


# what this function does for the service: Handles  preprocess for this service.
def _preprocess(img):
    """Improve OCR accuracy for scanned PDFs."""
    return img.convert("L").point(lambda p: 255 if p > 180 else 0).filter(ImageFilter.SHARPEN)


# what this function does for the service: Handles  normalize text for this service.
def _normalize_text(text):
    text = text.replace("\r", "\n").replace("\xa0", " ")
    text = text.replace("ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“", "-").replace("ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# what this function does for the service: Handles  looks like usable text for this service.
def _looks_like_usable_text(text):
    stripped = text.strip()
    if len(stripped) < 80:
        return False

    alpha_count = sum(ch.isalpha() for ch in stripped)
    return alpha_count >= 40


# what this function does for the service: Handles  extract text with pymupdf for this service.
def _extract_text_with_pymupdf(pdf_bytes):
    if fitz is None:
        return ""

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


# what this function does for the service: Handles  extract text with pypdf for this service.
def _extract_text_with_pypdf(pdf_bytes):
    if PdfReader is None:
        return ""

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


# what this function does for the service: Handles pdf bytes to text for this service.
def pdf_bytes_to_text(pdf_bytes, dpi=200):
    """Extract text from a PDF with OCR fallback for scanned pages."""
    direct_text = ""

    for extractor in (_extract_text_with_pymupdf, _extract_text_with_pypdf):
        try:
            candidate = _normalize_text(extractor(pdf_bytes))
        except Exception:
            continue

        if _looks_like_usable_text(candidate):
            return candidate

        if not direct_text and candidate:
            direct_text = candidate

    images = convert_from_bytes(pdf_bytes, dpi=dpi)
    ocr_text = "\n\n".join(
        pytesseract.image_to_string(_preprocess(img), lang="eng")
        for img in images
    )
    ocr_text = _normalize_text(ocr_text)

    if _looks_like_usable_text(ocr_text):
        return ocr_text

    return direct_text or ocr_text


# what this function does for the service: Handles  find for this service.
def _find(pattern, text, flags=re.IGNORECASE):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


# what this function does for the service: Handles  find money for this service.
def _find_money(pattern, text):
    raw = _find(pattern, text)
    if not raw:
        return None

    try:
        return float(re.sub(r"[^\d.]", "", raw))
    except ValueError:
        return None


# what this function does for the service: Handles  next non empty line for this service.
def _next_non_empty_line(lines, start_index):
    for idx in range(start_index, len(lines)):
        value = lines[idx].strip()
        if value:
            return value, idx
    return None, start_index


# what this function does for the service: Handles  find multiline value for this service.
def _find_multiline_value(pattern, text, flags=re.IGNORECASE):
    """Extract a value that may span multiple lines after a label."""
    match = re.search(pattern, text, flags)
    if not match:
        return None

    value = match.group(1).strip()
    value = re.sub(r"\s*\n\s*", " ", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value or None


# what this function does for the service: Handles find labelled value for this service.
def _find_label_value(label, text, stop_labels=None):
    """Extract a value after a label until the next known label or line ending."""
    if not label:
        return None

    stop_labels = stop_labels or []
    stop_pattern = "|".join(re.escape(item) for item in stop_labels if item)
    if stop_pattern:
        pattern = rf"{label}\s*[:\s]+\s*(.+?)(?=\s+(?:{stop_pattern})\s*[:\s]+|$)"
        return _find_multiline_value(pattern, text, re.IGNORECASE | re.DOTALL)

    return _find_multiline_value(rf"{label}\s*[:\s]+\s*(.+?)(?:$)", text, re.IGNORECASE | re.DOTALL)


# what this function does for the service: Handles find amount between labels for this service.
def _find_money_between_labels(label, text, stop_labels=None):
    raw = _find_label_value(label, text, stop_labels=stop_labels)
    if not raw:
        return None

    try:
        return float(re.sub(r"[^\d.]", "", raw))
    except ValueError:
        return None


# what this function does for the service: Handles normalize text token for this service.
def _clean_inline_value(value):
    if not value:
        return None

    value = re.sub(r"\s{2,}", " ", value).strip(" :-")
    return value or None


# what this function does for the service: Handles normalize document reference for this service.
def _normalize_reference_value(value):
    cleaned = _clean_inline_value(value)
    if not cleaned:
        return None

    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned.upper().startswith("CPF-"):
        cleaned = cleaned.replace(" ", "")
    return cleaned


# what this function does for the service: Handles extract standard income for this service.
def extract_standard_income(text):
    if re.search(r"CPF\s+CONTRIBUTION\s+HISTORY", text, re.IGNORECASE):
        document_variant = "cpf_contribution_history"
    elif re.search(r"EMPLOYEE\s+INCOME\s+STATEMENT", text, re.IGNORECASE):
        document_variant = "employee_income_statement"
    elif re.search(r"PAYSLIP\s+SUMMARY", text, re.IGNORECASE):
        document_variant = "payslip_summary"
    else:
        document_variant = "standard_income_statement"

    employer_raw = (
        _find_multiline_value(
            r"Employer Name[:\s]*(.+?)(?:\n(?:Employer UEN|Employment Type|Designation|Occupation|Years of Service)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        or _find_multiline_value(
            r"Employer\s*/\s*Source[:\s]*(.+?)(?=\s+(?:UEN\s*/\s*Tax\s*Ref|Employer\s+UEN|Employment Type|Designation|Occupation|Years of Service)\s*[:\s]+|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        or _find(r"Employment Income\s*\(([^)]+)\)", text)
    )

    full_name = _find_multiline_value(
        r"(?:Full Name(?: \(as per NRIC\))?|Employee Name)[:\s]*(.+?)(?:\n(?:Statement Reference|Reference No\.?|Application Ref(?:erence)?(?: No\.?)?|NRIC|Date of Birth|Date of Issue|Employer|Designation)|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    total_gross = (
        _find_money(r"TOTAL GROSS INCOME[^:]*:\s+S?\$?\s*([\d,]+\.?\d*)", text)
        or _find_money(r"Total Annual Gross Income\s*\(\d{4}\)[:\s]+S?\$?\s*([\d,]+\.?\d*)", text)
        or _find_money(r"TOTAL INCOME[:\s]+([\d,]+\.?\d*)", text)
        or _find_money(r"Total Gross Revenue.*?:\s+S?\$?\s*([\d,]+\.?\d*)", text)
    )

    avg_monthly = (
        _find_money(r"Average Monthly(?:\s+Gross)?\s+Income[^:]*:\s+S?\$?\s*([\d,]+\.?\d*)", text)
        or _find_money(r"Average Monthly Gross[:\s]+S?\$?\s*([\d,]+\.?\d*)", text)
        or _find_money(r"Average Monthly Net Income[:\s]+S?\$?\s*([\d,]+\.?\d*)", text)
    )

    doc_ref = (
        _normalize_reference_value(_find_label_value(
            r"Reference No\.?",
            text,
            stop_labels=["NRIC", "Date of Issue", "Date of Birth", "Period Covered", "Nationality"],
        ))
        or
        _find(r"Statement Reference[:\s]+(CPF-[\w-]+)", text)
        or _find(r"(?:Document Ref|NOA Reference|Application Ref(?:erence)?(?: No\.?)?)[:\s]+([\w-]+)", text)
        or _find(r"Ref[:\s]+([A-Z0-9-]+)", text)
    )

    period = (
        _find(r"Period Covered[:\s]+([^\n]+?)(?=\s+(?:Nationality|Residential Status|EMPLOYER|Employer)|$)", text)
        or
        _find_multiline_value(
            r"Statement Period[:\s]*(.+?)(?:\n(?:Nationality|Resid(?:ency|ential)\s+Status|EMPLOYER DETAILS)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        or _find(r"Employment Period[:\s]+([^\n]+)", text)
        or _find(r"Year of Assessment[:\s]+(\d{4})", text)
        or _find(r"INCOME DECLARATION\s*-\s*([A-Z]{3}\s+\d{4}\s*-\s*[A-Z]{3}\s+\d{4})", text)
    )

    return {
        "document_variant": document_variant,
        "full_name": full_name,
        "nric": _find(r"NRIC(?:\s*/\s*UIN)?(?:\s+(?:Number|No\.?))?[:\s]+([A-Z]\d{7}[A-Z])", text),
        "date_of_birth": _find(r"Date of Birth[:\s]+(\d{1,2}\s+\w+\s+\d{4})", text),
        "nationality": _find(r"Nationality[:\s]+([^\n]+)", text),
        "residency_status": _find(r"Resid(?:ency|ential)\s+Status[:\s]+([^\n]+)", text),
        "employer_name": " ".join(employer_raw.split()) if employer_raw else None,
        "employer_uen": (
            _find(r"Employer UEN[:\s]+(\w+)", text)
            or _find(r"UEN\s*/\s*Tax\s*Ref[:\s]+([A-Z0-9]+)", text)
        ),
        "employment_type": _find(r"Employment Type[:\s]+([^\n]+)", text),
        "occupation": _find(r"(?:Occupation|Designation)[:\s]+([^\n]+)", text),
        "total_ordinary_wages": _find_money(r"Total Ordinary Wages[^:]*:\s+S?\$?\s*([\d,]+\.\d{2})", text),
        "total_additional_wages": _find_money(r"Total Additional Wages[^:]*:\s+S?\$?\s*([\d,]+\.\d{2})", text),
        "total_gross_income": total_gross,
        "average_monthly_income": avg_monthly,
        "statement_reference": doc_ref,
        "statement_period": period,
        "date_of_issue": _find(r"Date of Issue[:\s]+(\d{1,2}\s+\w+\s+\d{4})", text),
    }


# what this function does for the service: Handles extract self employed income for this service.
def extract_self_employed_income(text):
    return {
        "document_variant": "self_employed_income_declaration",
        "full_name": _find_multiline_value(
            r"Full Name \(as per NRIC\)[:\s]*(.+?)(?:\n(?:Application Ref(?: No\.?)?|NRIC Number|Date of Submission)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        ),
        "nric": _find(r"NRIC(?: Number)?[:\s]+([A-Z]\d{7}[A-Z])", text),
        "date_of_birth": _find(r"Date of Birth[:\s]+(\d{1,2}\s+\w+\s+\d{4})", text),
        "residency_status": _find(r"Residential Status[:\s]+([^\n]+)", text),
        "employment_type": "Self-Employed",
        "occupation": _find_multiline_value(
            r"Nature of Business[:\s]*(.+?)(?:\n(?:Business Entity|UEN|Business Address)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        ),
        "business_entity": _find(r"Business Entity[:\s]+([^\n]+)", text),
        "business_uen": _find(r"UEN \(if registered\)[:\s]+([A-Z0-9]+)", text),
        "years_in_operation": _find(r"Years in Operation[:\s]+([^\n]+)", text),
        "total_gross_income": _find_money(r"Total Gross Revenue \(2024\)[:\s]+S?\$?\s*([\d,]+\.?\d*)", text),
        "total_business_expenses": _find_money(r"Total Business Expenses \(2024\)[:\s]+S?\$?\s*([\d,]+\.?\d*)", text),
        "net_self_employed_income": _find_money(r"NET SELF-EMPLOYED INCOME \(2024\)[:\s]+S?\$?\s*([\d,]+\.?\d*)", text),
        "average_monthly_income": _find_money(r"Average Monthly Net Income[:\s]+S?\$?\s*([\d,]+\.?\d*)", text),
        "statement_reference": _find(r"(?:Application Ref(?: No\.?)?|Ref)[:\s]+([\w-]+)", text),
        "statement_period": (
            _find(r"INCOME DECLARATION\s*-\s*([A-Z]{3}\s+\d{4}\s+TO\s+[A-Z]{3}\s+\d{4})", text)
            or _find(r"INCOME DECLARATION\s*-\s*([A-Z]{3}\s+\d{4}\s*-\s*[A-Z]{3}\s+\d{4})", text)
        ),
        "date_of_issue": _find(r"Date of Submission[:\s]+(\d{1,2}\s+\w+\s+\d{4})", text),
        "cpf_medisave_contribution": _find_money(
            r"CPF MediSave Contribution \(2024\)[:\s]+S?\$?\s*([\d,]+\.?\d*)",
            text,
        ),
    }


# what this function does for the service: Handles  extract joint income applicants for this service.
def _extract_joint_income_applicants(text):
    applicants = []

    for applicant_number in (1, 2):
        header_pattern = rf"APPLICANT {applicant_number}\b.*?(?=APPLICANT {applicant_number}\s+[—-]\s+MONTHLY INCOME|APPLICANT {applicant_number}\s*-\s*MONTHLY INCOME|JOINT HOUSEHOLD INCOME SUMMARY|$)"
        block_match = re.search(header_pattern, text, re.IGNORECASE | re.DOTALL)
        if not block_match:
            continue

        block = block_match.group(0)
        annual_gross = _find_money(
            rf"Applicant {applicant_number} Annual Gross.*?:\s+S?\$?\s*([\d,]+\.?\d*)",
            text,
        )
        average_monthly = _find_money(
            rf"Bank Account \(Applicant {applicant_number}\):.*?Average Monthly Gross:\s+S?\$?\s*([\d,]+\.?\d*)",
            text,
        )

        applicants.append(
            {
                "applicant_number": applicant_number,
                "name": _find_multiline_value(
                    r"Full Name[:\s]*(.+?)(?=\s+(?:Application Ref|NRIC|Date of Issue|Date of Birth|Nationality|Employer)\s*[:\s]+|$)",
                    block,
                    re.IGNORECASE | re.DOTALL,
                ),
                "nric": _find(r"NRIC[:\s]+([A-Z]\d{7}[A-Z])", block),
                "date_of_birth": _find(r"Date of Birth[:\s]+(\d{1,2}\s+\w+\s+\d{4})", block),
                "nationality": _find(r"Nationality[:\s]+([^\n]+)", block),
                "employer_name": _find_multiline_value(
                    r"Employer[:\s]*(.+?)(?=\s+(?:Designation|Employment Type|Years of Service|APPLICANT \d+\s+[—-]\s+MONTHLY INCOME|APPLICANT \d+\s*-\s*MONTHLY INCOME)\s*[:\s]+|$)",
                    block,
                    re.IGNORECASE | re.DOTALL,
                ),
                "employment_type": _find(r"Employment Type[:\s]+([^\n]+)", block),
                "occupation": _find(r"Designation[:\s]+([^\n]+)", block),
                "annual_gross_income": annual_gross,
                "average_monthly_income": average_monthly,
            }
        )

    return applicants


# what this function does for the service: Handles extract joint income for this service.
def extract_joint_income(text):
    applicants = _extract_joint_income_applicants(text)
    main_applicant = applicants[0] if applicants else {}

    return {
        "document_variant": "joint_household_income_statement",
        "full_name": main_applicant.get("name"),
        "nric": main_applicant.get("nric"),
        "date_of_birth": main_applicant.get("date_of_birth"),
        "employer_name": main_applicant.get("employer_name"),
        "employment_type": main_applicant.get("employment_type"),
        "occupation": main_applicant.get("occupation"),
        "statement_reference": _find(r"(?:Application Ref|Ref)[:\s]+([\w-]+)", text),
        "statement_period": _find(r"MONTHLY INCOME\s*\(([A-Z]{3}\s+\d{4}\s*(?:-|—)\s*[A-Z]{3}\s+\d{4})\)", text),
        "date_of_issue": _find(r"Date of Issue[:\s]+(\d{1,2}\s+\w+\s+\d{4})", text),
        "total_gross_income": _find_money(r"COMBINED ANNUAL GROSS INCOME[:\s]+S?\$?\s*([\d,]+\.?\d*)", text),
        "average_monthly_income": _find_money(r"COMBINED AVERAGE MONTHLY GROSS[:\s]+S?\$?\s*([\d,]+\.?\d*)", text),
        "hdb_income_ceiling_status": _find_multiline_value(
            r"HDB Income Ceiling Compliance[:\s]*(.+?)(?:\n(?:This joint income statement|Housing & Development Board)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        ),
        "applicants": applicants,
    }


# what this function does for the service: Handles extract income for this service.
def extract_income(text):
    """Extract fields from the supported income document variants."""
    if re.search(r"JOINT\s+INCOME\s+STATEMENT|JOINT\s+HOUSEHOLD\s+INCOME\s+DECLARATION", text, re.IGNORECASE):
        return extract_joint_income(text)

    if re.search(r"SELF-EMPLOYED\s+INCOME\s+DECLARATION|NET\s+SELF-EMPLOYED\s+INCOME", text, re.IGNORECASE):
        return extract_self_employed_income(text)

    return extract_standard_income(text)


# what this function does for the service: Handles  extract applicants for this service.
def _extract_applicants(text):
    """Parse applicant blocks from an HFE letter."""
    applicants = []

    for applicant_num in (1, 2):
        block_match = re.search(
            rf"Applicant\s+{applicant_num}\s+Name[:\s].*?(?=Applicant\s+{applicant_num + 1}\s+Name[:\s]|HFE\s+Reference\s+No\.?|MyDoc\s+Reference\s+No\.?|Date\s+of\s+Issue[:\s]|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not block_match:
            continue

        block = block_match.group(0)
        name = _find_multiline_value(
            rf"Applicant\s+{applicant_num}\s+Name[:\s]*(.+?)(?=\s+Applicant\s+{applicant_num}\s+NRIC/UIN\s+No\.?|\s+NRIC/UIN\s+No\.?|\s+Role[:\s]|$)",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        nric = _find(rf"Applicant\s+{applicant_num}\s+NRIC/UIN\s+No\.?[:\s]+([A-Z]\d{{7}}[A-Z])", block)
        if not nric:
            nric = _find(r"NRIC/UIN\s+No\.?[:\s]+([A-Z]\d{7}[A-Z])", block)
        role = _find_multiline_value(
            r"Role[:\s]*(.+?)(?=\s+Residential Status[:\s]|\s+Applicant\s+\d+\s+Name[:\s]|\s+HFE\s+Reference\s+No\.?|$)",
            block,
            re.IGNORECASE | re.DOTALL,
        )

        applicants.append(
            {
                "applicant_number": applicant_num,
                "name": _clean_inline_value(name),
                "nric": _clean_inline_value(nric),
                "role": _clean_inline_value(role),
            }
        )

    return applicants


# what this function does for the service: Handles extract hfe for this service.
def extract_hfe(text):
    assessment_outcome = (
        _find_label_value(
            r"Assessment\s+Outcome",
            text,
            stop_labels=["Housing Grants Eligibility", "Grant Type", "Important Notes", "Total Grants Eligible"],
        )
        or (
            "NOT ELIGIBLE"
            if re.search(r"HFE\s+letter\s+Not\s+Approved|NOT\s+approved|NOT\s+ELIGIBLE", text, re.IGNORECASE)
            else "ELIGIBLE" if re.search(r"HFE\s+letter\s+Approved|\bELIGIBLE\b", text, re.IGNORECASE) else None
        )
    )

    return {
        "applicants": _extract_applicants(text),
        "hfe_reference_no": _find(r"HFE\s+Reference\s+No\.?\s*[:\s]+(\S+)", text),
        "mydoc_reference_no": _find(r"MyDoc\s+Reference\s+No\.?\s*[:\s]+(\S+)", text),
        "date_of_issue": _find(r"Date\s+of\s+Issue[:\s]+(\d{1,2}\s+\w+\s+\d{4})", text),
        "valid_until": _find(r"[Vv]alid\s+until\s+(\d{1,2}\s+\w+\s+\d{4})", text),
        "eligible_flat_types": _find_label_value(
            r"Eligible\s+Flat\s+Type\(s\)",
            text,
            stop_labels=["Application Scheme", "HDB Loan Ceiling", "Income Assessment", "Description"],
        ),
        "application_scheme": _find_label_value(
            r"Application\s+Scheme",
            text,
            stop_labels=["HDB Loan Ceiling", "Income Assessment", "Description", "Applicant 1", "A Singapore Government Agency Website"],
        ),
        "hdb_loan_ceiling": _find_money_between_labels(
            r"HDB\s+Loan\s+Ceiling",
            text,
            stop_labels=["Income Assessment", "Description", "Applicant 1", "Total Household Monthly Income"],
        ),
        "total_household_income": (
            _find_money_between_labels(
                r"Combined\s+Household\s+Monthly\s+Income",
                text,
                stop_labels=["Income Ceiling", "Income Ceiling Status", "Combined Annual Income", "Assessment Outcome"],
            )
            or _find_money_between_labels(
                r"Total\s+Household\s+Monthly\s+Income",
                text,
                stop_labels=["Income Ceiling", "Income Ceiling Status", "Annual Income", "Assessment Outcome"],
            )
            or _find_money(
                r"Total\s+Household\s+(?:Monthly\s+)?Income\s*[:\s]*([\d,]+\.?\d*)",
                text,
            )
        ),
        "assessment_outcome": _clean_inline_value(assessment_outcome),
        "income_ceiling_status": _find_label_value(
            r"Income\s+Ceiling\s+Status",
            text,
            stop_labels=["Combined Annual Income", "Annual Income", "Assessment Outcome", "Housing Grants Eligibility"],
        ),
        "combined_annual_income": (
            _find_money_between_labels(
                r"Combined\s+Annual\s+Income\s+\(NOA\s+YA\d{4}\)",
                text,
                stop_labels=["Assessment Outcome", "Housing Grants Eligibility", "Grant Type"],
            )
            or _find_money_between_labels(
                r"Annual\s+Income\s+\(NOA\s+YA\d{4}\)",
                text,
                stop_labels=["Assessment Outcome", "Housing Grants Eligibility", "Grant Type"],
            )
        ),
        "total_grants_eligible": _find_money(
            r"Total\s+Grants?\s+Eligible[:\s]+(?:Up\s+to\s+)?S?\$?\s*([\d,]+)",
            text,
        ),
    }


# what this function does for the service: Handles normalize income result for this service.
def normalize_income_result(fields):
    variant = fields.get("document_variant")
    if variant == "joint_household_income_statement":
        applicants = fields.get("applicants") or []
        main_applicant = applicants[0] if len(applicants) > 0 else {}
        co_applicant = applicants[1] if len(applicants) > 1 else {}
        return {
            "main_applicant_name": main_applicant.get("name"),
            "main_applicant_nric": main_applicant.get("nric"),
            "main_applicant_date_of_birth": main_applicant.get("date_of_birth"),
            "main_applicant_nationality": main_applicant.get("nationality"),
            "main_applicant_employer_name": main_applicant.get("employer_name"),
            "main_applicant_employment_type": main_applicant.get("employment_type"),
            "main_applicant_occupation": main_applicant.get("occupation"),
            "main_applicant_average_monthly_income": main_applicant.get("average_monthly_income"),
            "co_applicant_name": co_applicant.get("name"),
            "co_applicant_nric": co_applicant.get("nric"),
            "co_applicant_date_of_birth": co_applicant.get("date_of_birth"),
            "co_applicant_nationality": co_applicant.get("nationality"),
            "co_applicant_employer_name": co_applicant.get("employer_name"),
            "co_applicant_employment_type": co_applicant.get("employment_type"),
            "co_applicant_occupation": co_applicant.get("occupation"),
            "co_applicant_average_monthly_income": co_applicant.get("average_monthly_income"),
            "template": "income_joint_applicants",
            "document_variant": variant,
            "statement_reference": fields.get("statement_reference"),
            "statement_period": fields.get("statement_period"),
            "date_of_issue": fields.get("date_of_issue"),
            "combined_total_gross_income": fields.get("total_gross_income"),
            "combined_average_monthly_income": fields.get("average_monthly_income"),
            "hdb_income_ceiling_status": fields.get("hdb_income_ceiling_status"),
        }

    return {
        "main_applicant_name": fields.get("full_name"),
        "main_applicant_nric": fields.get("nric"),
        "main_applicant_date_of_birth": fields.get("date_of_birth"),
        "main_applicant_nationality": fields.get("nationality"),
        "main_applicant_residency_status": fields.get("residency_status"),
        "main_applicant_employer_name": fields.get("employer_name"),
        "main_applicant_employer_uen": fields.get("employer_uen"),
        "main_applicant_employment_type": fields.get("employment_type"),
        "main_applicant_occupation": fields.get("occupation"),
        "co_applicant_name": None,
        "co_applicant_nric": None,
        "co_applicant_date_of_birth": None,
        "co_applicant_nationality": None,
        "co_applicant_residency_status": None,
        "co_applicant_employer_name": None,
        "co_applicant_employer_uen": None,
        "co_applicant_employment_type": None,
        "co_applicant_occupation": None,
        "template": "income_single_applicant",
        "document_variant": variant,
        "statement_reference": fields.get("statement_reference"),
        "statement_period": fields.get("statement_period"),
        "date_of_issue": fields.get("date_of_issue"),
        "total_ordinary_wages": fields.get("total_ordinary_wages"),
        "total_additional_wages": fields.get("total_additional_wages"),
        "total_gross_income": fields.get("total_gross_income"),
        "average_monthly_income": fields.get("average_monthly_income"),
        "cpf_medisave_contribution": fields.get("cpf_medisave_contribution"),
        "business_entity": fields.get("business_entity"),
        "business_uen": fields.get("business_uen"),
        "years_in_operation": fields.get("years_in_operation"),
        "net_self_employed_income": fields.get("net_self_employed_income"),
    }


# what this function does for the service: Handles normalize hfe result for this service.
def normalize_hfe_result(fields):
    applicants = fields.get("applicants") or []
    main_applicant = applicants[0] if len(applicants) > 0 else {}
    co_applicant = applicants[1] if len(applicants) > 1 else {}
    return {
        "main_applicant_name": main_applicant.get("name"),
        "main_applicant_nric": main_applicant.get("nric"),
        "main_applicant_role": main_applicant.get("role"),
        "co_applicant_name": co_applicant.get("name"),
        "co_applicant_nric": co_applicant.get("nric"),
        "co_applicant_role": co_applicant.get("role"),
        "template": "hfe_joint_applicants" if len(applicants) > 1 else "hfe_single_applicant",
        "hfe_reference_no": fields.get("hfe_reference_no"),
        "mydoc_reference_no": fields.get("mydoc_reference_no"),
        "date_of_issue": fields.get("date_of_issue"),
        "valid_until": fields.get("valid_until"),
        "eligible_flat_types": fields.get("eligible_flat_types"),
        "application_scheme": fields.get("application_scheme"),
        "hdb_loan_ceiling": fields.get("hdb_loan_ceiling"),
        "total_household_income": fields.get("total_household_income"),
        "assessment_outcome": fields.get("assessment_outcome"),
        "total_grants_eligible": fields.get("total_grants_eligible"),
    }


# what this function does for the service: Handles  parse optional int for this service.
def _parse_optional_int(raw_value, field_name):
    value = (raw_value or "").strip()
    if not value:
        return None, None

    try:
        return int(value), None
    except ValueError:
        return None, f"{field_name} must be an integer."


# what this function does for the service: Handles  parse required int for this service.
def _parse_required_int(raw_value, field_name):
    value = (raw_value or "").strip()
    if not value:
        return None, f"{field_name} is required."

    try:
        return int(value), None
    except ValueError:
        return None, f"{field_name} must be an integer."


# what this function does for the service: Handles detect doc type for this service.
def detect_doc_type(text):
    # Check income variants first so HDB-branded income letters are not
    # mistaken for HFE letters.
    if re.search(r"JOINT\s+INCOME\s+STATEMENT|JOINT\s+HOUSEHOLD\s+INCOME\s+DECLARATION", text, re.IGNORECASE):
        return "income"
    if re.search(r"SELF-EMPLOYED\s+INCOME\s+DECLARATION|INCOME\s+DECLARATION\s+FOR\s+BTO", text, re.IGNORECASE):
        return "income"
    if re.search(r"CPF\s+CONTRIBUTION\s+HISTORY", text, re.IGNORECASE):
        return "income"
    if re.search(r"CENTRAL\s+PROVIDENT\s+FUND", text, re.IGNORECASE) and re.search(
        r"income|wages|contribution", text, re.IGNORECASE
    ):
        return "income"
    if re.search(r"EMPLOYEE\s+INCOME\s+STATEMENT", text, re.IGNORECASE):
        return "income"
    if re.search(r"PAYSLIP\s+SUMMARY", text, re.IGNORECASE):
        return "income"
    if re.search(r"NOTICE\s+OF\s+ASSESSMENT", text, re.IGNORECASE) and re.search(
        r"INLAND\s+REVENUE|IRAS", text, re.IGNORECASE
    ):
        return "income"
    if re.search(r"INLAND\s+REVENUE\s+AUTHORITY", text, re.IGNORECASE) and re.search(
        r"income|assessment", text, re.IGNORECASE
    ):
        return "income"
    if re.search(r"HDB\s+Flat\s+Eligibility\s+\(HFE\)\s+Letter", text, re.IGNORECASE):
        return "hfe"
    if re.search(r"HDB\s+Flat\s+Eligib", text, re.IGNORECASE):
        return "hfe"
    if re.search(r"HFE\s+letter", text, re.IGNORECASE):
        return "hfe"
    if re.search(r"Flat\s+Eligibility\s+(Letter|Assessment)", text, re.IGNORECASE):
        return "hfe"
    if re.search(r"HFE\s+Reference\s+No", text, re.IGNORECASE):
        return "hfe"
    if re.search(r"Housing\s+&\s+Development\s+Board", text, re.IGNORECASE) and re.search(
        r"eligible\s+flat\s+type|hdb\s+loan\s+ceiling|total\s+grants?\s+eligible|assessment\s+outcome",
        text,
        re.IGNORECASE,
    ):
        return "hfe"
    return "unknown"


# what this function does for the service: Handles process document upload for this service.
def process_document_upload(uploaded_file, application_id):
    filename = uploaded_file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported."}, 400

    pdf_bytes = uploaded_file.read()
    if not pdf_bytes:
        return {"error": "Uploaded PDF is empty."}, 400

    document_hash = hashlib.sha256(pdf_bytes).hexdigest()
    stored_filename = f"{document_hash}.pdf"
    storage_path = STORAGE_DIR / stored_filename
    storage_path.write_bytes(pdf_bytes)

    initial_doc_type = "unknown"
    document = save_document_record(
        application_id=application_id,
        document_type=initial_doc_type,
        storage_path=storage_path,
        status="uploaded",
        fields=None,
    )
    document_id = document.document_id

    try:
        text = pdf_bytes_to_text(pdf_bytes)
        print(f"[OCR] Extracted text for {filename} ({document_id}):\n{text}\n", flush=True)
    except Exception as exc:
        update_document_record(document_id, "unknown", "failed", None)
        return {"error": f"Failed to process PDF: {exc}", "document_id": document_id}, 500

    document_type = detect_doc_type(text)

    if document_type == "income":
        fields = normalize_income_result(extract_income(text))
    elif document_type == "hfe":
        fields = normalize_hfe_result(extract_hfe(text))
    else:
        update_document_record(document_id, "unknown", "failed", None)
        return {
            "error": "Could not identify document type. Expected an income document or HFE letter.",
            "document_id": document_id,
        }, 422

    update_document_record(document_id, document_type, "processed", fields)
    return {
        "document_id": document_id,
        "application_id": application_id,
        "document_type": document_type,
        "status": "processed",
        "fields": fields,
    }, 200


# what this function does for the service: Handles extract for this service.
@app.route("/extract", methods=["POST"])
def extract():
    """
    Extract structured fields from a PDF and persist the uploaded document
    ---
    tags:
      - OCR
    operationId: extractDocument
    summary: Extract document fields from an income PDF or HFE letter
    description: |
      Main OCR endpoint used by the frontend upload flow.
      The service accepts a PDF upload, stores the raw file in the mounted data volume,
      auto-detects whether the file is an income document or an HFE letter, extracts
      structured fields, and stores the metadata plus OCR result in MySQL.
    consumes:
      - multipart/form-data
    produces:
      - application/json
    requestBody:
      required: true
      content:
        multipart/form-data:
          schema:
            type: object
            required:
              - file
            properties:
              file:
                type: string
                format: binary
                description: PDF file to extract.
              application_id:
                type: integer
                description: Application identifier stored with the document record.
          example:
            application_id: 2001
    responses:
      200:
        description: OCR extraction completed successfully and the document was stored.
        content:
          application/json:
            example:
              document_id: 1
              application_id: 1001
              document_type: income
              status: processed
              fields:
                main_applicant_name: AARON TAN
                main_applicant_nric: S8501234A
                co_applicant_name: null
                co_applicant_nric: null
                template: income_single_applicant
                statement_reference: CPF-2025-STM-00841
                average_monthly_income: 7233.33
      400:
        description: Missing file, missing application_id, unsupported upload type, or invalid application_id.
        content:
          application/json:
            examples:
              missingFile:
                value:
                  error: "No file uploaded. Send a PDF as form-data field 'file'."
              invalidApplicationId:
                value:
                  error: "application_id is required."
      422:
        description: Document type could not be identified from the PDF contents.
        content:
          application/json:
            example:
              error: "Could not identify document type. Expected an income document or HFE letter."
              document_id: 5
      500:
        description: Unexpected OCR processing failure.
        content:
          application/json:
            example:
              error: "Failed to process PDF: OCR engine error"
              document_id: 5
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Send a PDF as form-data field 'file'."}), 400

    uploaded = request.files["file"]
    application_id, application_id_error = _parse_required_int(request.form.get("application_id"), "application_id")
    if application_id_error:
        return jsonify({"error": application_id_error}), 400

    payload, status_code = process_document_upload(uploaded, application_id)
    return jsonify(payload), status_code


# what this function does for the service: Handles list documents for this service.
@app.route("/documents", methods=["GET"])
def list_documents():
    """
    List stored document records
    ---
    tags:
      - Documents
    operationId: listDocuments
    summary: List persisted document metadata
    produces:
      - application/json
    parameters:
      - in: query
        name: application_id
        required: false
        schema:
          type: integer
        description: Optional application filter.
        example: 1001
    responses:
      200:
        description: Matching documents returned successfully.
        content:
          application/json:
            example:
              documents:
                - document_id: 2
                  application_id: 1001
                  document_type: hfe
                  storage_path: /data/documents/680f0088996184fbaf52b56f142c8e0375b67682f34b3a2d641208246242cf4b.pdf
                  status: processed
                  fields:
                    main_applicant_name: AARON TAN WEI MING
                    co_applicant_name: null
                    template: hfe_single_applicant
                    hfe_reference_no: 25189218A
                  uploaded_at: "2026-03-30 09:05:00"
      400:
        description: Invalid application_id query parameter.
        content:
          application/json:
            example:
              error: "application_id must be an integer."
    """
    application_id, application_id_error = _parse_optional_int(request.args.get("application_id"), "application_id")
    if application_id_error:
        return jsonify({"error": application_id_error}), 400

    query = db.select(Document).order_by(Document.uploaded_at.desc())
    if application_id is not None:
        query = query.where(Document.application_id == application_id)

    documents = db.session.scalars(query).all()
    return jsonify({"documents": [document.to_dict() for document in documents]})


# what this function does for the service: Handles get document for this service.
@app.route("/documents/<int:document_id>", methods=["GET"])
def get_document(document_id):
    """
    Get stored document metadata and OCR fields
    ---
    tags:
      - Documents
    operationId: getDocument
    summary: Read a persisted document record
    produces:
      - application/json
    parameters:
      - in: path
        name: document_id
        required: true
        schema:
          type: integer
        example: 1
    responses:
      200:
        description: Document metadata returned successfully.
        content:
          application/json:
            example:
              document_id: 1
              application_id: 1001
              document_type: income
              storage_path: /data/documents/f8fb51382d183fd5d7c23563cc1276cf62c0e5c69b0f3929b2f0bb59ad72fb91.pdf
              status: processed
              fields:
                main_applicant_name: AARON TAN
                co_applicant_name: null
                template: income_single_applicant
                total_gross_income: 86800
              uploaded_at: "2026-03-30 09:00:00"
      404:
        description: No document exists for the supplied id.
        content:
          application/json:
            example:
              error: "Document not found."
    """
    row = get_document_record(document_id)
    if row is None:
        return jsonify({"error": "Document not found."}), 404

    return jsonify(row.to_dict())


# what this function does for the service: Handles get document file for this service.
@app.route("/documents/<int:document_id>/file", methods=["GET"])
def get_document_file(document_id):
    """
    Download or preview the stored PDF for a document record
    ---
    tags:
      - Documents
    operationId: getDocumentFile
    summary: Return the raw stored PDF
    produces:
      - application/pdf
      - application/json
    parameters:
      - in: path
        name: document_id
        required: true
        schema:
          type: integer
        example: 1
    responses:
      200:
        description: PDF returned successfully.
        content:
          application/pdf:
            schema:
              type: string
              format: binary
      404:
        description: No document exists for the supplied id.
        content:
          application/json:
            examples:
              missingDocument:
                value:
                  error: "Document not found."
              missingFile:
                value:
                  error: "Stored PDF could not be found on disk."
    """
    row = get_document_record(document_id)
    if row is None:
        return jsonify({"error": "Document not found."}), 404

    storage_path = Path(row.storage_path or "")
    if not row.storage_path or not storage_path.exists():
        return jsonify({"error": "Stored PDF could not be found on disk."}), 404

    return send_file(
        storage_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"document-{document_id}.pdf",
    )


init_storage()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
