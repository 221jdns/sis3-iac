#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
PREFIX="${1:-sis3-dev}"
TOPIC=$(out "$PREFIX-foundation" TopicArn)
DLQ=$(out "$PREFIX-foundation" DLQUrl)
EVENT="poison-$(date +%s)-$RANDOM"
aws sns publish --topic-arn "$TOPIC" \
  --message "{\"eventId\":\"$EVENT\",\"orderId\":\"bad-order\",\"eventType\":\"OrderCreated\",\"forceFail\":true}"
echo "Poison event: $EVENT"
echo "Wait roughly 3-6 minutes, sometimes longer. Then inspect DLQ:"
echo "aws sqs receive-message --queue-url '$DLQ' --wait-time-seconds 20 --visibility-timeout 10 --max-number-of-messages 10"
