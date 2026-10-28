#!/usr/bin/env bash
# Push the app to an existing Hugging Face Space (Docker SDK).
# Usage: bash deploy/deploy_hf_space.sh <hf-username>/<space-name>
# Before running: create the Space on huggingface.co (SDK: Docker, blank template, CPU basic) and
# add the secret NEBIUS_API_KEY (and optionally TERMPLAN_MODEL) in the Space settings.
# Git asks for your Hugging Face username and an access token with write scope.
set -euo pipefail
SPACE="${1:?usage: deploy_hf_space.sh <hf-username>/<space-name>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git clone "https://huggingface.co/spaces/${SPACE}" "$WORK/space"
cd "$WORK/space"
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$ROOT/termplan" "$ROOT/examples" "$ROOT/Dockerfile" "$ROOT/requirements.txt" "$ROOT/LICENSE" .
cp "$ROOT/deploy/hf-space/README.md" README.md
find . -name __pycache__ -type d -prune -exec rm -rf {} +
git add -A
git commit -m "Deploy Termplan" || echo "nothing to commit"
git push
echo "Pushed. Build logs: https://huggingface.co/spaces/${SPACE}?logs=build"
echo "App URL: https://$(echo "$SPACE" | tr '/' '-' | tr '[:upper:]' '[:lower:]').hf.space"
