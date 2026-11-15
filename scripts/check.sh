#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
PREFIX="${1:-sis3-dev}"
URL=$(out "$PREFIX-app" ServiceUrl)
TABLE=$(out "$PREFIX-foundation" TableName)
LOG=$(out "$PREFIX-foundation" ConsumerLogGroup)
EVENT="event-$(date +%s)-$RANDOM"
echo "URL=$URL EVENT=$EVENT TABLE=$TABLE"
curl --fail-with-body "$URL/health"; echo
BODY="{\"orderId\":\"order-001\",\"eventId\":\"$EVENT\"}"
for n in 1 2; do
  CODE=$(curl -sS -o /tmp/sis3-response.json -w '%{http_code}' \
    -H 'Content-Type: application/json' -d "$BODY" "$URL/orders")
  cat /tmp/sis3-response.json; echo
  [[ "$CODE" == 202 ]] || { echo "Expected 202, got $CODE"; exit 1; }
done
KEY="{\"eventId\":{\"S\":\"$EVENT\"}}"
FOUND=false
for n in $(seq 1 30); do
  STATUS=$(aws dynamodb get-item --table-name "$TABLE" --key "$KEY" \
    --consistent-read --query 'Item.status.S' --output text)
  if [[ "$STATUS" == PROCESSED ]]; then FOUND=true; break; fi
  sleep 5
done
[[ "$FOUND" == true ]] || { echo "No processed result"; exit 1; }
aws dynamodb get-item --table-name "$TABLE" --key "$KEY" --consistent-read
CODE=$(curl -sS -o /tmp/sis3-invalid.json -w '%{http_code}' \
  -H 'Content-Type: application/json' -d '{}' "$URL/orders")
[[ "$CODE" == 400 ]] || { echo "Expected 400, got $CODE"; exit 1; }
echo "Health, accepted requests, stored result, invalid input: PASS"
echo "Now verify processed AND duplicate_skipped for $EVENT in log group $LOG"
echo "aws logs tail '$LOG' --since 10m --format short"
