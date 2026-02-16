#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

echo "=== Alfred Deployment ==="

# The .env file must exist with non-sensitive config filled in.
# Copy .env.example to .env and fill in values for your deployment.
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Copy .env.example and fill in values."
    exit 1
fi

echo "Fetching secrets from GCP Secret Manager..."

# Read GCP_PROJECT_ID from .env
GCP_PROJECT=$(grep -E '^GCP_PROJECT_ID=' "$ENV_FILE" | cut -d= -f2-)
if [[ -z "$GCP_PROJECT" ]]; then
    echo "ERROR: GCP_PROJECT_ID must be set in .env"
    exit 1
fi

fetch_secret() {
    local secret_name="$1"
    local required="${2:-true}"
    local value
    value=$(gcloud secrets versions access latest --secret="$secret_name" --project="$GCP_PROJECT" 2>/dev/null) || true
    if [[ -z "$value" && "$required" == "true" ]]; then
        echo "ERROR: Failed to fetch required secret: $secret_name"
        exit 1
    fi
    echo "$value"
}

# Fetch secrets and append/overwrite them in .env
# First, strip any previously-injected secrets (between markers)
sed -i '/^# --- INJECTED SECRETS ---$/,/^# --- END SECRETS ---$/d' "$ENV_FILE"

DB_PASSWORD="$(fetch_secret alfred-db-password)"
DB_USER=$(grep -E '^DB_USER=' "$ENV_FILE" | cut -d= -f2-)
DB_HOST=$(grep -E '^DB_HOST=' "$ENV_FILE" | cut -d= -f2-)
DB_PORT=$(grep -E '^DB_PORT=' "$ENV_FILE" | cut -d= -f2-)
DB_NAME=$(grep -E '^DB_NAME=' "$ENV_FILE" | cut -d= -f2-)

cat >> "$ENV_FILE" <<EOF
# --- INJECTED SECRETS ---
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
JWT_SECRET=$(fetch_secret alfred-jwt-secret)
SLACK_BOT_TOKEN=$(fetch_secret alfred-slack-bot-token)
SLACK_SIGNING_SECRET=$(fetch_secret alfred-slack-signing-secret)
SLACK_APP_TOKEN=$(fetch_secret alfred-slack-app-token)
SLACK_CLIENT_SECRET=$(fetch_secret alfred-slack-client-secret)
TS_AUTHKEY=$(fetch_secret alfred-tailscale-authkey)
# --- END SECRETS ---
EOF

echo "Starting services..."
cd "$PROJECT_DIR"
docker compose -f docker-compose.prod.yml up -d

echo "Waiting for backend health check..."
MAX_RETRIES=30
RETRY=0
until docker compose -f docker-compose.prod.yml ps backend 2>/dev/null | grep -q "(healthy)"; do
    RETRY=$((RETRY + 1))
    if [[ $RETRY -ge $MAX_RETRIES ]]; then
        echo "ERROR: Backend failed to become healthy after $MAX_RETRIES attempts"
        docker compose -f docker-compose.prod.yml logs backend
        exit 1
    fi
    echo "  Waiting for backend... (attempt $RETRY/$MAX_RETRIES)"
    sleep 5
done

echo "=== Alfred is running ==="
docker compose -f docker-compose.prod.yml ps
