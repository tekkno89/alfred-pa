#!/bin/bash
# Pre-commit hook that blocks commits modifying sensitive paths.
# Installed by entrypoint.sh into .git/hooks/pre-commit during implement mode.
# Configurable via SENSITIVE_PATHS env var (comma-separated patterns).

SENSITIVE_PATHS="${SENSITIVE_PATHS:-.github/workflows,Dockerfile,docker-compose,.env,.secrets,*.pem,*.key}"

IFS=',' read -ra PATTERNS <<< "$SENSITIVE_PATHS"
STAGED=$(git diff --cached --name-only)

for file in $STAGED; do
  for pattern in "${PATTERNS[@]}"; do
    if [[ "$file" == *"$pattern"* ]]; then
      echo "BLOCKED: Cannot modify sensitive path: $file"
      exit 1
    fi
  done
done
