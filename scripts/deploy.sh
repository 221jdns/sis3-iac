#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PREFIX="${1:-sis3-dev}"
[[ "$PREFIX" =~ ^[a-z][a-z0-9-]{2,24}$ ]] || { echo "Invalid prefix"; exit 1; }
source scripts/env.sh
if [[ ! -x .venv/bin/python || ! -x node_modules/.bin/cdk ]]; then
  bash scripts/setup.sh
fi
CDK=./node_modules/.bin/cdk
# Bootstrap is shared per account and region, not per application copy.
if ! aws cloudformation describe-stacks --stack-name CDKToolkit >/dev/null 2>&1; then
  "$CDK" bootstrap "aws://$CDK_DEFAULT_ACCOUNT/$AWS_REGION"
fi
TAG=$(cat app/app.py app/Dockerfile app/requirements.txt | sha256sum | cut -c1-16)
"$CDK" synth -c prefix="$PREFIX" -c image_tag="$TAG" >/dev/null
.venv/bin/python tests/check_templates.py "$PREFIX"
"$CDK" deploy "$PREFIX-foundation" --exclusively \
  -c prefix="$PREFIX" -c image_tag="$TAG" --require-approval broadening
REPO=$(out "$PREFIX-foundation" RepositoryName)
URI=$(out "$PREFIX-foundation" RepositoryUri)
if aws ecr describe-images --repository-name "$REPO" \
     --image-ids imageTag="$TAG" >/dev/null 2>&1; then
  echo "Reusing immutable image $URI:$TAG"
else
  docker build --platform linux/amd64 -t "$URI:$TAG" ./app
  aws ecr get-login-password | docker login --username AWS \
    --password-stdin "${URI%%/*}"
  docker push "$URI:$TAG"
fi
"$CDK" deploy "$PREFIX-app" --exclusively \
  -c prefix="$PREFIX" -c image_tag="$TAG" --require-approval broadening
out "$PREFIX-app" ServiceUrl
