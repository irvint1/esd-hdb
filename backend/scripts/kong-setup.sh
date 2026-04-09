#!/bin/bash

# Kong Admin API setup script for esd-hdb
# Run this AFTER docker-compose.yml is up.
#
# Usage:
#   cd esd-hdb/backend
#   docker compose up --build -d
#   bash kong/setup.sh
#!/usr/bin/env bash
set -e

# Load .env if it exists
if [ -f "$(dirname "$0")/../.env" ]; then
  set -a
  source "$(dirname "$0")/../.env"
  set +a
fi


ADMIN=http://localhost:8001
ENABLE_PROCESS_BALLOT_KEY_AUTH=${ENABLE_PROCESS_BALLOT_KEY_AUTH:-true}

# Service URLs from .env
NETS_PAYMENT_SERVICE_URL=${NETS_PAYMENT_SERVICE_URL:-http://localhost:5003}
APPLICATION_SERVICE_URL=${APPLICATION_SERVICE_URL:-http://localhost:5004}
CHECK_ELIGIBILITY_SERVICE_URL=${CHECK_ELIGIBILITY_SERVICE_URL:-http://localhost:5008}
NOTIFICATION_SERVICE_URL=${NOTIFICATION_SERVICE_URL:-http://localhost:5015}
PROCESS_BALLOT_SERVICE_URL=${PROCESS_BALLOT_SERVICE_URL:-http://localhost:5011}
BALLOT_SERVICE_URL=${BALLOT_SERVICE_URL:-http://localhost:5005}
PROJECT_SERVICE_URL=${PROJECT_SERVICE_URL:-https://personal-iu6aefgj.outsystemscloud.com/ProjectsMicroservice/rest/ProjectsAPI}
VALIDATE_ELIGIBILITY_SERVICE_URL=${VALIDATE_ELIGIBILITY_SERVICE_URL:-http://localhost:5013}
FLAT_SELECTION_SERVICE_URL=${FLAT_SELECTION_SERVICE_URL:-http://localhost:5002}
FLAT_SERVICE_URL=${FLAT_SERVICE_URL:-http://localhost:5006}
SINGPASS_SERVICE_URL=${SINGPASS_SERVICE_URL:-http://localhost:5007}
MOCKPASS_URL=${MOCKPASS_URL:-http://localhost:5156}
DOCUMENT_SERVICE_URL=${DOCUMENT_SERVICE_URL:-http://localhost:5050}
HFE_APPLICATION_SERVICE_URL=${HFE_APPLICATION_SERVICE_URL:-http://localhost:5009}
OUTSYSTEMS_PROJECT_API_URL=${PROJECT_SERVICE_URL}

# Wait for Kong Admin API to be ready
echo "Waiting for Kong Admin API..."
until curl -sf "$ADMIN/status" > /dev/null; do
  sleep 2
done
echo "Kong is ready."

# ─── Helper ──────────────────────────────────────────────────────────────────
# create_service <name> <upstream-url>
create_service() {
  local name=$1
  local url=$2
  echo "  Registering service: $name -> $url"
  curl -sf -X PUT "$ADMIN/services/$name" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"$url\"}" > /dev/null
}

# create_route <service-name> <route-name> <path-or-regex> [methods-json]
# strip_path=false so the full path is forwarded to the upstream service.
# methods-json example: ["GET","POST"]
create_route() {
  local service=$1
  local route=$2
  local path=$3
  local methods_json=${4:-}

  local payload
  if [ -n "$methods_json" ]; then
    payload="{\"paths\": [\"$path\"], \"strip_path\": false, \"methods\": $methods_json}"
  else
    payload="{\"paths\": [\"$path\"], \"strip_path\": false}"
  fi

  echo "  Registering route:   $path -> $service"
  curl -sf -X PUT "$ADMIN/services/$service/routes/$route" \
    -H "Content-Type: application/json" \
    -d "$payload" > /dev/null
}

# ─── Scenario 1: Apply for BTO ───────────────────────────────────────────────
echo ""
echo "==> Scenario 1: Apply for BTO"

create_service "apply-bto"    "$APPLICATION_SERVICE_URL"
create_route   "apply-bto"    "apply-bto-initiate-route"       "/apply-bto/initiate"                        '["POST","OPTIONS"]'
create_route   "apply-bto"    "apply-bto-complete-route"       "~/apply-bto/complete/[^/]+$"               '["POST","OPTIONS"]'
create_route   "apply-bto"    "apply-bto-demo-force-route"     "~/apply-bto/demo-force-success/[^/]+$"     '["POST","OPTIONS"]'

create_service "singpass"     "$SINGPASS_SERVICE_URL"
create_route   "singpass"     "singpass-auth-login-route"       "/singpass/auth/login"                      '["GET","OPTIONS"]'
create_route   "singpass"     "singpass-auth-callback-route"    "/singpass/auth/callback"                   '["GET","OPTIONS"]'
create_route   "singpass"     "singpass-profile-route"          "/singpass/profile"                         '["GET","OPTIONS"]'
create_route   "singpass"     "singpass-logout-route"           "/singpass/logout"                          '["POST","OPTIONS"]'

create_service "nets-payment" "$NETS_PAYMENT_SERVICE_URL"
create_route   "nets-payment" "nets-payment-b2s-callback-route" "/payment/b2s-callback"                     '["GET","POST","OPTIONS"]'
create_route   "nets-payment" "nets-payment-s2s-callback-route" "/payment/s2s-callback"                     '["POST","OPTIONS"]'
create_route   "nets-payment" "nets-payment-abandon-route"      "~/payment/abandon/[^/]+$"                  '["POST","OPTIONS"]'
create_route   "nets-payment" "nets-payment-status-route"       "~/payment/status/[^/]+$"                   '["GET","OPTIONS"]'

create_service "document"     "$DOCUMENT_SERVICE_URL"
create_route   "document"     "document-extract-route"          "/extract"                                  '["POST","OPTIONS"]'
create_route   "document"     "document-route"                  "/documents"                                '["GET","OPTIONS"]'

# ─── Scenario 2: Ballot Run ──────────────────────────────────────────────────
echo ""
echo "==> Scenario 2: Ballot Run"

create_service "process-ballot" "$PROCESS_BALLOT_SERVICE_URL"
create_route   "process-ballot" "process-ballot-run-route"      "/process-ballot/run"                       '["POST","OPTIONS"]'

create_service "ballot-audit" "$BALLOT_SERVICE_URL"
create_route   "ballot-audit" "ballot-audit-list-create-route"  "/ballot-audits"                            '["GET","POST","OPTIONS"]'
create_route   "ballot-audit" "ballot-audit-update-route"       "~/ballot-audits/[0-9]+$"                   '["PUT","OPTIONS"]'

create_service "project"      "$PROJECT_SERVICE_URL"
create_route   "project"      "project-list-route"              "/projects"                                 '["GET","OPTIONS"]'

# ─── Scenario 3: Flat Selection ──────────────────────────────────────────────
echo ""
echo "==> Scenario 3: Flat Selection"

create_service "flat"           "$FLAT_SERVICE_URL"
create_route   "flat"           "flat-list-route"                  "/flats"                                   '["GET","OPTIONS"]'

create_service "flat-selection" "$FLAT_SELECTION_SERVICE_URL"
create_route   "flat-selection" "flat-selection-list-route"        "/flat-selection"                          '["GET","OPTIONS"]'

create_service "application"    "$APPLICATION_SERVICE_URL"
create_route   "application"    "application-list-route"           "/applications"                            '["GET","OPTIONS"]'

FLAT_ALLOCATION_URL=${FLAT_ALLOCATION_URL:-http://flat-allocation-service:5005}
create_service "flat-allocation" "$FLAT_ALLOCATION_URL"
create_route   "flat-allocation" "flat-allocation-select-route"    "/select-flat"                            '["POST","OPTIONS"]'
create_route   "flat-allocation" "flat-allocation-initiate-route"  "/select-flat/initiate"                   '["POST","OPTIONS"]'
create_route   "flat-allocation" "flat-allocation-complete-route"  "~/select-flat/complete/[^/]+$"          '["POST","OPTIONS"]'

# ─── Plugins ─────────────────────────────────────────────────────────────────
echo ""
echo "==> Applying plugins"

# Remove previously-created global CORS plugins so reruns stay deterministic.
for plugin_id in $(curl -s "$ADMIN/plugins?name=cors&size=1000" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data.get('data', []):
    if p.get('service') is None and p.get('route') is None and p.get('consumer') is None:
        print(p['id'])
"); do
  echo "  Removing stale global cors plugin: $plugin_id"
  curl -sf -X DELETE "$ADMIN/plugins/$plugin_id" > /dev/null
done

# Global CORS for browser requests from the Vue frontend through Kong.
echo "  Plugin: global cors"
curl -sf -X POST "$ADMIN/plugins" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cors",
    "config": {
      "origins": ["http://localhost:5173"],
      "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
      "headers": ["Accept", "Authorization", "Content-Type", "Origin", "X-Requested-With", "apikey"],
      "exposed_headers": ["Content-Length", "Content-Type"],
      "credentials": true,
      "max_age": 3600
    }
  }' > /dev/null

# Rate-limit apply-bto: max 5 submissions/minute per IP (prevents duplicate submissions)
echo "  Plugin: rate-limiting on apply-bto"
curl -sf -X POST "$ADMIN/services/apply-bto/plugins" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rate-limiting",
    "config": {
      "minute": 5,
      "hour": 20,
      "policy": "local"
    }
  }' > /dev/null

# Rate-limit flat-selection: max 30 requests/minute (prevents race conditions on reservation)
echo "  Plugin: rate-limiting on flat-selection"
curl -sf -X POST "$ADMIN/services/flat-selection/plugins" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rate-limiting",
    "config": {
      "minute": 30,
      "policy": "local"
    }
  }' > /dev/null

# API key auth on process-ballot is optional for local demos.
if [ "$ENABLE_PROCESS_BALLOT_KEY_AUTH" = "true" ]; then
  echo "  Plugin: key-auth on process-ballot"
  curl -sf -X POST "$ADMIN/routes/process-ballot-run-route/plugins" \
    -H "Content-Type: application/json" \
    -d '{"name": "key-auth"}' > /dev/null

  echo "  Plugin: key-auth on apply-bto demo-force-success"
  curl -sf -X POST "$ADMIN/routes/apply-bto-demo-force-route/plugins" \
    -H "Content-Type: application/json" \
    -d '{"name": "key-auth"}' > /dev/null

  # Create a consumer for the ballot-audit cron job and assign it an API key
  echo "  Consumer: ballot-cron-job"
  curl -sf -X PUT "$ADMIN/consumers/ballot-cron-job" \
    -H "Content-Type: application/json" \
    -d '{"username": "ballot-cron-job"}' > /dev/null

  echo "  API key: ballot-cron-job-secret"
  curl -sf -X PUT "$ADMIN/consumers/ballot-cron-job/key-auth/ballot-cron-job-secret" \
    -H "Content-Type: application/json" \
    -d '{"key": "ballot-cron-job-secret"}' > /dev/null
else
  echo "  Skipping key-auth on process-ballot (ENABLE_PROCESS_BALLOT_KEY_AUTH=false)"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "==> Kong setup complete. Registered services and routes:"
echo "   Login entrypoint is: http://localhost:8000/singpass/auth/login"
echo ""
curl -s "$ADMIN/services" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('data', []):
  name = s.get('name', '<unnamed>')
  upstream = s.get('url')
  if not upstream:
    protocol = s.get('protocol', 'http')
    host = s.get('host', '')
    port = s.get('port')
    path = s.get('path') or ''
    upstream = f'{protocol}://{host}'
    if port:
      upstream += f':{port}'
    if path and not path.startswith('/'):
      path = '/' + path
    upstream += path
  print(f\"  {name:20s} -> {upstream}\")
"
echo ""
echo "Active routes:"
curl -s "$ADMIN/routes" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('data', []):
    print(f\"  {str(r['paths']):30s} strip_path={r['strip_path']}\")
"
