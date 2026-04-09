import base64
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, make_response, redirect, request
from flask_cors import CORS
from flasgger import Swagger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MOCKPASS_URL = os.environ.get("MOCKPASS_URL", "http://localhost:5156")
MOCKPASS_BROWSER_URL = os.environ.get("MOCKPASS_BROWSER_URL", "http://localhost:5156")
MOCKPASS_AUTH_PATH = os.environ.get("MOCKPASS_AUTH_PATH", "/singpass/v2/auth")
MOCKPASS_CLIENT_ID = os.environ.get("MOCKPASS_CLIENT_ID", "hdb-flat-portal")
MOCKPASS_TIMEOUT_SECONDS = float(os.environ.get("MOCKPASS_TIMEOUT_SECONDS", "5"))

ENABLE_SESSIONS = os.environ.get("ENABLE_SESSIONS", "true").lower() == "true"
SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "60"))
AUTH_STATE_TIMEOUT_SECONDS = int(os.environ.get("AUTH_STATE_TIMEOUT_SECONDS", "300"))

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
FRONTEND_AUTH_CALLBACK_PATH = os.environ.get("FRONTEND_AUTH_CALLBACK_PATH", "/auth/callback")

SESSION_STORAGE: dict[str, dict[str, Any]] = {}
AUTH_STATE_STORAGE: dict[str, dict[str, Any]] = {}

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.logger.setLevel(os.environ.get("SINGPASS_LOG_LEVEL", "INFO").upper())

app.config["SWAGGER"] = {
    "title": "SingPass Wrapper API",
    "version": 1.0,
    "openapi": "3.0.2",
    "description": "MockPass wrapper with session management and legacy REST compatibility.",
}
Swagger(app)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_usage(action: str, status: str, source: str = "unknown", nric: str = "", detail: str = "") -> None:
    payload = {
        "event": "singpass_usage",
        "action": action,
        "status": status,
        "source": source,
        "nric": nric,
        "detail": detail,
        "backend": "mockpass",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    app.logger.info(json.dumps(payload))


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------

def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def create_session(nric: str, profile: dict[str, Any], source: str) -> str:
    token = generate_session_token()
    SESSION_STORAGE[token] = {
        "nric": nric,
        "profile": profile,
        "profile_source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat(),
    }
    return token


def validate_session(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None

    session = SESSION_STORAGE.get(token)
    if not session:
        return None

    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        del SESSION_STORAGE[token]
        return None

    return session


# ---------------------------------------------------------------------------
# Auth State Management
# ---------------------------------------------------------------------------

def cleanup_auth_states() -> None:
    now_utc = datetime.now(timezone.utc)
    expired = [
        state
        for state, record in AUTH_STATE_STORAGE.items()
        if datetime.fromisoformat(record["expires_at"]) <= now_utc
    ]
    for state in expired:
        del AUTH_STATE_STORAGE[state]


def sanitise_redirect_path(raw_path: Optional[str]) -> str:
    if not isinstance(raw_path, str):
        return "/"

    path = raw_path.strip()
    if not path.startswith("/") or path.startswith("//"):
        return "/"

    return path


def create_auth_state(redirect_path: str) -> Tuple[str, str]:
    cleanup_auth_states()

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(16)
    AUTH_STATE_STORAGE[state] = {
        "nonce": nonce,
        "redirect_path": sanitise_redirect_path(redirect_path),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=AUTH_STATE_TIMEOUT_SECONDS)).isoformat(),
    }
    return state, nonce


def consume_auth_state(state: Optional[str]) -> Optional[dict[str, Any]]:
    if not state:
        return None

    cleanup_auth_states()
    record = AUTH_STATE_STORAGE.pop(state, None)
    return record if isinstance(record, dict) else None


# ---------------------------------------------------------------------------
# MockPass + Persona Helpers
# ---------------------------------------------------------------------------

def decode_stateless_auth_code(code: str) -> Optional[dict[str, Any]]:
    try:
        padded = code + ("=" * (-len(code) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def normalize_profile_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, list):
        return [normalize_profile_value(item) for item in value]

    if isinstance(value, dict):
        # Already a MyInfo-like field
        if "value" in value or "code" in value or "desc" in value:
            return dict(value)

        return {
            key: normalize_profile_value(inner)
            for key, inner in value.items()
        }

    if isinstance(value, (str, int, float, bool)):
        return {"value": value}

    return value


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}

    return {
        key: normalize_profile_value(value)
        for key, value in profile.items()
    }


def read_numeric_profile_value(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, dict):
        for key in ("value", "amount", "$numberDecimal", "$numberDouble", "$numberInt"):
            if key in value:
                parsed = read_numeric_profile_value(value.get(key))
                if parsed is not None:
                    return parsed
        return None

    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    return None


def ensure_monthly_income(profile: dict[str, Any]) -> dict[str, Any]:
    """
    Keep a single consistent monthlyincome field in the wrapper response.
    """
    if not isinstance(profile, dict):
        return {}

    monthly_candidates = (
        profile.get("monthlyincome"),
        profile.get("average_monthly_income"),
        profile.get("monthlyIncome"),
        profile.get("monthly_income"),
    )
    monthly_income = next(
        (value for value in (read_numeric_profile_value(candidate) for candidate in monthly_candidates) if value is not None and value > 0),
        None,
    )

    if monthly_income is None:
        noa = profile.get("noa")
        annual_candidates = []
        if isinstance(noa, dict):
            annual_candidates.extend((noa.get("amount"), noa.get("employment")))
        annual_candidates.extend((
            profile.get("annualincome"),
            profile.get("annual_income"),
            profile.get("annualIncome"),
        ))
        annual_income = next(
            (value for value in (read_numeric_profile_value(candidate) for candidate in annual_candidates) if value is not None and value > 0),
            None,
        )
        if annual_income is not None:
            monthly_income = round(annual_income / 12, 2)

    enriched = dict(profile)
    if monthly_income is not None:
        enriched["monthlyincome"] = {"value": monthly_income}

    return enriched


def extract_display_name(profile: Optional[dict[str, Any]], fallback_nric: str) -> str:
    if isinstance(profile, dict):
        name_field = profile.get("name")
        if isinstance(name_field, dict):
            value = name_field.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
        elif isinstance(name_field, str) and name_field.strip():
            return name_field.strip()

    return fallback_nric


def build_persona_from_auth_payload(decoded_auth: dict[str, Any], nric: str) -> Tuple[Optional[dict[str, Any]], str]:
    """Extract persona from MockPass auth code.

    MockPass is configured with SINGPASS_CLIENT_PROFILE=full to include full MyInfo v3 claims.
    Auth code format:
    {
      "profile": {
        "nric": "S9812381D",
        "uuid": "a9865837-7bd7-46ac-bef4-42a76a946424",
        "claims": {
          "name": {"value": "TAN XIAO HUI"},
          "uinfin": {"value": "S9812381D"},
          ... (additional MyInfo v3 fields)
        }
      },
      "nonce": "XYZ789"
    }

    Expected: Claims will always be present with SINGPASS_CLIENT_PROFILE=full
    Fallback: If claims missing, uses NRIC as display name (should not happen with proper config)
    """
    if not isinstance(decoded_auth, dict):
        app.logger.error(f"Auth code is not a dict for {nric}")
        return None, "mockpass_invalid_format"

    # Extract profile object
    profile = decoded_auth.get("profile")
    if not isinstance(profile, dict):
        app.logger.error(f"Auth code missing profile object for {nric}", extra={
            "auth_keys": list(decoded_auth.keys())
        })
        return None, "mockpass_invalid_format"

    # Extract NRIC from auth code (should always be present)
    auth_nric = profile.get("nric", "").strip().upper()
    if not auth_nric:
        app.logger.error(f"Auth code profile missing nric field", extra={
            "nric_arg": nric,
            "profile_keys": list(profile.keys())
        })
        return None, "mockpass_invalid_format"

    # Try to extract claims from profile (optional - only if MockPass is configured to include them)
    claims = profile.get("claims")

    if isinstance(claims, dict) and claims:
        # MockPass provided full MyInfo v3 data in auth code - use it
        app.logger.info(f"Found claims in auth code for {auth_nric}")

        persona = ensure_monthly_income(normalize_profile(claims))

        # Ensure required fields exist
        if not persona.get("uinfin"):
            persona["uinfin"] = {"value": auth_nric}
        if not persona.get("name"):
            persona["name"] = {"value": auth_nric}

        app.logger.info(f"Successfully extracted persona from auth code claims for {auth_nric}")
        return persona, "mockpass_from_claims"

    # No claims in auth code - fetch full profile from MockPass MyInfo v3 test endpoint
    app.logger.info(f"No claims in auth code for {auth_nric} - fetching from MockPass MyInfo endpoint")
    
    try:
        myinfo_url = f"{MOCKPASS_URL}/myinfo/v3/test-person?uinfin={auth_nric}"
        myinfo_response = requests.get(myinfo_url, timeout=MOCKPASS_TIMEOUT_SECONDS)
        
        if myinfo_response.status_code == 200:
            profile_data = myinfo_response.json()
            # Ensure uinfin is set to the NRIC
            if "uinfin" not in profile_data:
                profile_data["uinfin"] = {"value": auth_nric}
            profile_data = ensure_monthly_income(normalize_profile(profile_data))
            app.logger.info(f"Successfully fetched full profile from MockPass for {auth_nric}")
            return profile_data, "mockpass_myinfo"
        else:
            app.logger.warning(f"MockPass MyInfo endpoint returned {myinfo_response.status_code} for {auth_nric}")
    except Exception as e:
        app.logger.warning(f"Failed to fetch from MockPass MyInfo endpoint: {str(e)}")

    # Fallback: create minimal persona with NRIC if fetch fails
    app.logger.info(f"Falling back to minimal persona for {auth_nric}")

    minimal_persona = {
        "uinfin": {"value": auth_nric},
        "name": {"value": auth_nric},  # Default: use NRIC as display name
    }

    # Add UUID if provided by MockPass
    uuid_value = profile.get("uuid")
    if uuid_value:
        minimal_persona["uuid"] = {"value": str(uuid_value)}

    app.logger.info(f"Created minimal persona from auth code for {auth_nric}")
    return ensure_monthly_income(minimal_persona), "mockpass_minimal"


def build_frontend_callback_url(
    status: str,
    redirect_path: str = "/",
    nric: str = "",
    name: str = "",
    message: str = "",
) -> str:
    base = FRONTEND_URL.rstrip("/")
    callback_path = FRONTEND_AUTH_CALLBACK_PATH
    if not callback_path.startswith("/"):
        callback_path = f"/{callback_path}"

    query: dict[str, str] = {"status": status}
    if redirect_path and redirect_path != "/":
        query["redirect"] = redirect_path
    if nric:
        query["nric"] = nric
    if name:
        query["name"] = name
    if message:
        query["message"] = message

    return f"{base}{callback_path}?{urlencode(query)}"


def build_public_base_url() -> str:
    """Resolve the externally reachable base URL when behind Kong/reverse proxies."""
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").strip()
    forwarded_host = request.headers.get("X-Forwarded-Host", "").strip()
    forwarded_port = request.headers.get("X-Forwarded-Port", "").strip()

    if forwarded_host:
        proto = forwarded_proto or request.scheme or "http"
        host = forwarded_host.split(",", 1)[0].strip()

        # Kong may forward host without port. Preserve external port when provided.
        if forwarded_port and ":" not in host:
            default_port = "443" if proto == "https" else "80"
            if forwarded_port != default_port:
                host = f"{host}:{forwarded_port}"

        return f"{proto}://{host}"

    return request.host_url.rstrip("/")


def build_mockpass_auth_url(redirect_path: str, login_hint: str = "") -> str:
    """Build MockPass authorize URL for the current request context."""
    state, nonce = create_auth_state(redirect_path)

    params = {
        "response_type": "code",
        "client_id": MOCKPASS_CLIENT_ID,
        "redirect_uri": f"{build_public_base_url()}/singpass/auth/callback",
        "scope": "openid",
        "state": state,
        "nonce": nonce,
    }

    if login_hint:
        params["login_hint"] = login_hint

    return f"{MOCKPASS_BROWSER_URL.rstrip('/')}{MOCKPASS_AUTH_PATH}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/singpass/auth/login", methods=["GET"])
def singpass_auth_login():
    """Start browser login flow by redirecting to MockPass authorize endpoint."""
    redirect_path = sanitise_redirect_path(request.args.get("redirect"))
    login_hint = request.args.get("login_hint", "").strip()  # OIDC standard parameter
    auth_url = build_mockpass_auth_url(redirect_path, login_hint=login_hint)

    log_usage(
        action="auth_start",
        status="redirect",
        source="mockpass",
        detail=f"redirect={redirect_path}" + (f" login_hint={login_hint}" if login_hint else ""),
    )

    return redirect(auth_url)


@app.route("/singpass/login", methods=["GET", "POST", "OPTIONS"])
def legacy_singpass_login():
    """Backward-compatible login endpoint used by older frontend builds."""
    if request.method == "OPTIONS":
        return "", 204

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}

    redirect_path = sanitise_redirect_path(
        payload.get("redirect")
        or request.args.get("redirect")
    )
    login_hint = str(
        payload.get("login_hint")
        or payload.get("nric")
        or payload.get("applicant_nric")
        or request.args.get("login_hint")
        or ""
    ).strip()

    auth_url = build_mockpass_auth_url(redirect_path, login_hint=login_hint)
    log_usage(
        action="auth_start_legacy",
        status="redirect",
        source="mockpass",
        detail=f"redirect={redirect_path}" + (f" login_hint={login_hint}" if login_hint else ""),
    )

    if request.method == "GET":
        return redirect(auth_url)

    return jsonify(
        {
            "code": 200,
            "data": {
                "login_url": auth_url,
                "redirect_path": redirect_path,
            },
        }
    ), 200


@app.route("/singpass/auth/callback", methods=["GET"])
def singpass_auth_callback():
    """Handle MockPass callback, create local session, then redirect frontend."""
    state = request.args.get("state")
    code = request.args.get("code")
    auth_error = request.args.get("error")

    state_record = consume_auth_state(state)
    redirect_path = sanitise_redirect_path((state_record or {}).get("redirect_path"))

    if auth_error:
        log_usage("auth_callback", "error", "mockpass", detail=f"reason=provider_error redirect={redirect_path}")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path=redirect_path,
                message="MockPass authentication was cancelled.",
            )
        )

    if not state_record:
        log_usage("auth_callback", "error", "mockpass", detail="reason=invalid_or_expired_state")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path="/",
                message="Authentication state is invalid or expired. Please try again.",
            )
        )

    if not isinstance(code, str) or not code.strip():
        log_usage("auth_callback", "error", "mockpass", detail=f"reason=missing_code redirect={redirect_path}")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path=redirect_path,
                message="Missing authorization code from MockPass.",
            )
        )

    decoded_auth = decode_stateless_auth_code(code.strip())
    if decoded_auth is None:
        log_usage("auth_callback", "error", "mockpass", detail=f"reason=decode_failed redirect={redirect_path}")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path=redirect_path,
                message="Unable to decode MockPass auth code.",
            )
        )

    expected_nonce = state_record.get("nonce")
    received_nonce = decoded_auth.get("nonce")
    if expected_nonce and received_nonce and expected_nonce != received_nonce:
        log_usage("auth_callback", "error", "mockpass", detail=f"reason=nonce_mismatch redirect={redirect_path}")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path=redirect_path,
                message="Authentication nonce validation failed. Please try again.",
            )
        )

    profile = decoded_auth.get("profile")
    raw_nric = profile.get("nric") if isinstance(profile, dict) else None
    if not isinstance(raw_nric, str) or not raw_nric.strip():
        log_usage("auth_callback", "error", "mockpass", detail=f"reason=missing_nric redirect={redirect_path}")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path=redirect_path,
                message="MockPass callback did not include an NRIC.",
            )
        )

    nric = raw_nric.strip().upper()
    persona, source = build_persona_from_auth_payload(decoded_auth, nric)
    if persona is None:
        if source == "mockpass_invalid_format":
            reason = "invalid_format"
            message = (
                "Unable to process your login. The authentication server returned data we couldn't read. "
                "Please try again or contact support if this persists."
            )
        elif source == "mockpass_not_found":
            reason = "profile_not_found"
            message = "No profile found for this NRIC. Please check and try again."
        else:
            reason = "profile_unavailable"
            message = "Unable to reach the authentication server. Please try again."
        
        app.logger.error(f"Failed to build persona: {reason} for {nric}", extra={
            "reason": reason,
            "source": source,
            "redirect_path": redirect_path
        })
        log_usage("auth_callback", "error", "mockpass", nric=nric, detail=f"reason={reason} redirect={redirect_path}")
        return redirect(
            build_frontend_callback_url(
                status="error",
                redirect_path=redirect_path,
                message=message,
            )
        )

    # MockPass is configured to include full MyInfo claims in auth code
    # Extract and use them directly (no separate profile fetch needed)

    app.logger.info(f"Extracted persona for {nric}", extra={
        "persona_keys": list(persona.keys()),
        "source": source
    })

    name = extract_display_name(persona, nric)

    response = make_response(
        redirect(
            build_frontend_callback_url(
                status="success",
                redirect_path=redirect_path,
                nric=nric,
                name=name,
            )
        ),
        302,
    )

    if ENABLE_SESSIONS:
        token = create_session(nric, persona, source)
        response.set_cookie(
            "singpass_session",
            token,
            max_age=SESSION_TIMEOUT_MINUTES * 60,
            httponly=True,
            secure=False,
            samesite="Strict",
            path="/",
        )

    log_usage("auth_callback", "success", "mockpass", nric=nric, detail=f"redirect={redirect_path}")
    return response

@app.route("/singpass/profile", methods=["GET"])
def get_profile():
    """Get MyInfo profile by session (when no NRIC is supplied) or explicit NRIC.

    Behavior:
    - With `nric` query param: fetch directly from MockPass MyInfo v3 test endpoint.
    - Without `nric`: return session profile if a valid session exists.
    """
    raw_nric = request.args.get("nric")
    requested_nric = raw_nric.strip().upper() if isinstance(raw_nric, str) and raw_nric.strip() else ""

    # Explicit NRIC lookup takes precedence so callers can request a full
    # profile deterministically without being shadowed by session payload shape.
    if not requested_nric and ENABLE_SESSIONS:
        token = request.cookies.get("singpass_session")
        if token:
            session = validate_session(token)
            if session:
                source = str(session.get("profile_source", "unknown"))
                payload = ensure_monthly_income(dict(session.get("profile") or {}))
                payload["_source"] = source
                payload["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
                log_usage(
                    "profile",
                    "success",
                    source,
                    nric=str(session.get("nric", "")),
                    detail="retrieved_from=session"
                )
                return jsonify(payload)

            log_usage("profile", "invalid_session", "session")
            if not requested_nric:
                return jsonify({"error": "Session expired or invalid"}), 401

    # No valid session - try explicit NRIC
    if not requested_nric:
        if ENABLE_SESSIONS:
            log_usage(
                "profile",
                "unauthorized",
                "session",
                detail="reason=missing_nric_and_no_valid_session"
            )
            return jsonify({"error": "Session required or provide nric."}), 401

        log_usage("profile", "invalid_request", "request", detail="reason=missing_nric")
        return jsonify({"error": "nric is required."}), 400

    # For explicit NRIC lookup: Fetch from MockPass MyInfo v3 test endpoint
    app.logger.info(f"Fetching full profile for {requested_nric} from MockPass MyInfo endpoint")

    try:
        myinfo_url = f"{MOCKPASS_URL}/myinfo/v3/test-person?uinfin={requested_nric}"
        myinfo_response = requests.get(myinfo_url, timeout=MOCKPASS_TIMEOUT_SECONDS)

        if myinfo_response.status_code == 200:
            profile_data = ensure_monthly_income(normalize_profile(myinfo_response.json()))
            profile_data["_source"] = "mockpass_myinfo_v3"
            profile_data["_retrieved_at"] = datetime.now(timezone.utc).isoformat()
            app.logger.info(
                "Prepared MyInfo profile for %s with monthlyincome=%s",
                requested_nric,
                ((profile_data.get("monthlyincome") or {}).get("value") if isinstance(profile_data.get("monthlyincome"), dict) else None),
            )

            log_usage(
                "profile",
                "success",
                "mockpass_myinfo_v3",
                nric=requested_nric,
                detail="retrieved_from=myinfo_endpoint"
            )
            return jsonify(profile_data), 200

        elif myinfo_response.status_code == 404:
            app.logger.warning(f"Profile not found in MyInfo for {requested_nric}")
            log_usage(
                "profile",
                "not_found",
                "mockpass_myinfo_v3",
                nric=requested_nric,
                detail="reason=nric_not_in_test_data"
            )
            return jsonify({
                "error": "Profile not found",
                "nric": requested_nric,
                "message": f"No test profile available for {requested_nric}",
            }), 404

        else:
            app.logger.error(f"MyInfo endpoint returned {myinfo_response.status_code}")
            log_usage(
                "profile",
                "error",
                "mockpass_myinfo_v3",
                nric=requested_nric,
                detail=f"http_status={myinfo_response.status_code}"
            )
            return jsonify({"error": "Failed to retrieve profile"}), 502

    except requests.exceptions.RequestException as error:
        app.logger.error(f"MyInfo endpoint request failed: {str(error)}")
        log_usage(
            "profile",
            "error",
            "mockpass_myinfo_v3",
            nric=requested_nric,
            detail=f"request_failed={type(error).__name__}"
        )
        return jsonify({"error": "Unable to reach profile service"}), 503


@app.route("/singpass/logout", methods=["POST"])
def singpass_logout():
    """Destroy local session and clear cookie."""
    if not ENABLE_SESSIONS:
        log_usage("logout", "sessions_disabled", "session")
        return jsonify({"error": "Sessions not enabled"}), 400

    token = request.cookies.get("singpass_session")
    session = SESSION_STORAGE.get(token) if token else None
    if token and token in SESSION_STORAGE:
        del SESSION_STORAGE[token]

    response = make_response(jsonify({"status": "logged_out"}), 200)
    response.set_cookie(
        "singpass_session",
        "",
        max_age=0,
        httponly=True,
        secure=False,
        samesite="Strict",
        path="/",
    )

    log_usage(
        action="logout",
        status="success",
        source=str((session or {}).get("profile_source", "session")),
        nric=str((session or {}).get("nric", "")),
    )
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5007, debug=False)
