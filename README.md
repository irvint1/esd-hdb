# esd-hdb

## Singpass Test Setup

This repository now includes:

- `test.py`: Python utility for:
	- API test (`client_credentials` + API call)
	- Local backend endpoint for authorization code exchange
- `frontend/`: Browser UI to test Singpass login flow (authorization redirect + callback inspector)

## 1) Install Python dependency

```bash
pip install requests
```

## 2) Set environment variables (PowerShell)

```powershell
$env:SINGPASS_TOKEN_URL="https://your-token-endpoint"
$env:SINGPASS_CLIENT_ID="your-client-id"
$env:SINGPASS_CLIENT_SECRET="your-client-secret"
$env:SINGPASS_SCOPE="openid"
```

Optional:

```powershell
$env:SINGPASS_VERIFY_SSL="true"
$env:SINGPASS_TIMEOUT="20"
```

## 3) Run the backend code exchange endpoint

```bash
python test.py server --host 127.0.0.1 --port 5000
```

This exposes:

- `POST http://127.0.0.1:5000/exchange-code`

Expected JSON body:

```json
{
	"code": "<authorization_code>",
	"code_verifier": "<pkce_code_verifier>",
	"redirect_uri": "http://localhost:8000/frontend/index.html"
}
```

## 4) Serve the frontend locally

From repository root:

```bash
python -m http.server 8000
```

Then open:

- `http://localhost:8000/frontend/index.html`

## 5) Test login in browser

1. Fill in `Authorization Endpoint`, `Client ID`, `Redirect URI`, `Scope`.
2. Set `Response Type` to `code`.
3. Set `Backend Token Exchange Endpoint` to `http://127.0.0.1:5000/exchange-code`.
4. Click **Login With Singpass**.
5. After redirect back, click **Exchange Code Via Backend**.

## 6) Run API mode test (existing functionality)

Set:

```powershell
$env:SINGPASS_API_URL="https://your-api-endpoint"
$env:SINGPASS_HTTP_METHOD="GET"
```

Then:

```bash
python test.py api
```