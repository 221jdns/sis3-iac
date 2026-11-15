#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
PREFIX="${1:?Usage: bash scripts/destroy.sh sis3-check}"
[[ "$PREFIX" =~ ^[a-z][a-z0-9-]{2,24}$ ]] || exit 1
printf 'Delete %s-app and %s-foundation including data/images? Type prefix: ' "$PREFIX" "$PREFIX"
read -r ANSWER
[[ "$ANSWER" == "$PREFIX" ]] || exit 1
./node_modules/.bin/cdk destroy "$PREFIX-app" --force -c prefix="$PREFIX"
./node_modules/.bin/cdk destroy "$PREFIX-foundation" --force -c prefix="$PREFIX"
