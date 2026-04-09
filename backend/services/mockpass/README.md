# MockPass Integration for HDB Flat Portal

## Overview

This directory wraps **MockPass** — a mock Singpass/MyInfo v3 server for development — with custom test data and scenarios for the HDB BTO application system.

## Source & Attribution

- **MockPass Repository**: [@opengovsg/mockpass](https://github.com/opengovsg/mockpass)
- **Package**: `npm install @opengovsg/mockpass`
- **Version**: As specified in package.json
- **License**: Check upstream repo (typically GPL/open source)

MockPass is maintained by the Government Technology Agency of Singapore (GovTech) and provides mock implementations of:
- SingPass v2 (OIDC) / v3 (FAPI)
- MyInfo v3 (Person endpoint)
- Corppass v2
- sgID v2

## Why MockPass Instead of Real SingPass?

1. **Development convenience** - No need for real SingPass credentials
2. **Test data control** - Can create specific personas and scenarios
3. **No external dependencies** - Runs locally, always available
4. **Cost-free** - No per-call charges

## How We Extended MockPass

### 1. Custom Test Data (v3.json)

**File**: `v3.json` (in this directory)

This file defines all test personas with their MyInfo data:

```json
{
  "personas": {
    "S9812381D": {
      "name": {"value": "TAN HENG HUAT"},
      "sex": {"code": "F", "desc": "FEMALE"},
      "dob": {"value": "1998-06-06"},
      "noa": {
        "amount": {"value": 64400},
        "employment": {"value": 64400}
      },
      "monthlyincome": {"value": 5366.67},
      ... more fields
    },
    "S9912364H": { ... },
    ... 28 more test personas
  }
}
```

**Why we manage this here:**
- Keeps demo scenarios in version control
- Easy to add new test cases
- Reflects real MyInfo v3 schema


### 2. Custom Server Wrapper (server.js)

**File**: `server.js` (in this directory)

**What it does:**
- Starts MockPass on internal port 5157
- Exposes a proxy on port 5156 for external access
- Adds custom endpoint: `GET /myinfo/v3/test-person?uinfin={NRIC}`
  - This endpoint directly returns MyInfo data from `v3.json`
  - Derives `monthlyincome` from annual income if needed

**Why this approach:**
```
Standard MockPass flow:
  1. SingPass auth code exchange → returns claims in ID token
  2. Separate token call → get access token
  3. GET /myinfo/v3/person → uses access token

Our simplified flow:
  1. SingPass auth code → includes claims directly ✓
  2. No separate token needed ✓
  3. GET /myinfo/v3/test-person → direct lookup from v3.json ✓
```

## Why We Didn't Use Standard MyInfo Info Endpoints

### The Problem with Standard Flow

Real MyInfo has **two separate authentication layers**:

```
Layer 1: OAuth2 (for SingPass)
  - Client credentials flow
  - Returns ID token with user consent

Layer 2: PKI/Signature Verification (for MyInfo API)
  - Need X.509 certificates
  - Need to sign requests with private keys
  - Need to verify response signatures
  - Complex key rotation management
```

**Each layer has**:
- Separate credentials (OAuth client_id/secret ≠ PKI certs)
- Separate validation logic
- Separate failure modes
- Separate rate limiting

### Why That's Overkill for Demo

In a demo, we need:
1. ✅ Realistic data (MyInfo fields) → Use v3.json
2. ✅ Easy access (no PKI setup) → Custom test endpoint
3. ✅ Multiple test personas → Hardcoded scenarios
4. ❌ Real security validation ← Not needed for demo

### Our Simplification

Instead of the complex 2-layer auth, we:

1. **Include claims in auth code**
   - MockPass can be configured with `SINGPASS_CLIENT_PROFILE=full`
   - Auth code contains full MyInfo claims
   - No separate info call needed

2. **Provide test endpoint**
   - `GET /myinfo/v3/test-person?uinfin=S9812381D`
   - Returns MyInfo data from v3.json
   - No signature verification, no certificate handling

3. **Store data in version control**
   - All test personas in `v3.json`
   - Demo scenarios documented in DEMO_SCENARIOS_ACTUAL.md
   - Easy to maintain and extend

```
Real Flow (Production):
  Frontend
    ↓
  SingPass OAuth
    ↓
  Get ID Token + consent
    ↓
  Call MyInfo /person endpoint
    ↓ (requires PKI verification)
  Return encrypted MyInfo data
    ↓ (requires decryption with private key)
  Frontend gets data

Our Demo Flow:
  Frontend
    ↓
  SingPass OAuth
    ↓
  Get auth code with claims embedded
    ↓
  Call /myinfo/v3/test-person
    ↓ (no PKI, just lookup v3.json)
  Frontend gets data ✓
```

## Setup & Running

### 1. Install Dependencies
```bash
cd mockpass
npm install
```

### 2. Configure Environment
```bash
# Optional: point to custom v3.json
export MYINFO_V3_PATH=/path/to/v3.json

# Port (default 5156)
export PORT=5156
```

### 3. Start the Server
```bash
npm start
# or
node server.js
```

### 4. Test Endpoints

**MockPass SingPass v2:**
```bash
curl "http://localhost:5156/singpass/v2/auth?response_type=code&client_id=hdb-flat-portal&redirect_uri=http://localhost:5007/singpass/auth/callback&scope=openid"
```

**Custom Test Endpoint (our addition):**
```bash
curl "http://localhost:5156/myinfo/v3/test-person?uinfin=S9812381D"
```

Returns:
```json
{
  "uinfin": {"value": "S9812381D"},
  "name": {"value": "TAN HENG HUAT"},
  "sex": {"code": "F", "desc": "FEMALE"},
  ...
}
```

## Files in This Directory

| File | Purpose |
|------|---------|
| `server.js` | Custom wrapper for MockPass |
| `v3.json` | Test personas data (31 scenarios) |
| `README.md` | This file |
| `package.json` | Node dependencies |

## Migrating to Real SingPass

When moving to production:

1. **Remove custom server.js** - Use real SingPass endpoints
2. **Remove v3.json** - Data comes from real MyInfo API
3. **Add PKI certificates** - For MyInfo API signature verification
4. **Update credentials** - Real SingPass client_id/secret

The application logic remains the same:
- SingPass OAuth flow is identical
- MyInfo field names are identical
- Session handling is identical
- Only the data source changes (mock → real)

## Resources

- [MockPass Repo](https://github.com/opengovsg/mockpass)
- [SingPass Documentation](https://docs.developer.singpass.gov.sg/)
- [MyInfo v3 API](https://www.myinfo.gov.sg/)
