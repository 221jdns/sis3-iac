#!/usr/bin/env bash
export AWS_REGION="${AWS_REGION:-eu-north-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""
export CDK_DEFAULT_REGION="$AWS_REGION"
export CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
out() {
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue | [0]" \
    --output text
}

export JSII_RUNTIME_PACKAGE_CACHE=disabled
