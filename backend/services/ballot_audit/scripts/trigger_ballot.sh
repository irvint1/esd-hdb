#!/usr/bin/env sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <exercise_id> [process_ballot_url]"
  exit 1
fi

EXERCISE_ID="$1"
PROCESS_BALLOT_URL="${2:-${PROCESS_BALLOT_URL:-http://localhost:5011}}"

curl -sS -X POST "$PROCESS_BALLOT_URL/process-ballot/run" \
  -H "Content-Type: application/json" \
  -d "{\"exercise_id\": $EXERCISE_ID}"
