#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

# Read domains from .env
APP_DOMAIN=$(grep -E '^APP_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)
SLACK_DOMAIN=$(grep -E '^SLACK_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)

GCP_PROJECT=$(grep -E '^GCP_PROJECT_ID=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$APP_DOMAIN" || -z "$SLACK_DOMAIN" ]]; then
    echo "ERROR: APP_DOMAIN and SLACK_DOMAIN must be set in .env"
    exit 1
fi

if [[ -z "$GCP_PROJECT" ]]; then
    echo "ERROR: GCP_PROJECT_ID must be set in .env"
    exit 1
fi

# Fetch Cloudflare token from GCP Secret Manager
echo "Fetching Cloudflare API token from GCP Secret Manager..."
CF_TOKEN=$(gcloud secrets versions access latest --secret="alfred-cloudflare-api-token" --project="$GCP_PROJECT")
cat > "$SCRIPT_DIR/cloudflare.ini" <<EOF
dns_cloudflare_api_token = ${CF_TOKEN}
EOF
chmod 600 "$SCRIPT_DIR/cloudflare.ini"

EMAIL=$(grep -E '^CERTBOT_EMAIL=' "$ENV_FILE" | cut -d= -f2- 2>/dev/null || echo "admin@${APP_DOMAIN}")

echo "=== SSL Certificate Setup (Cloudflare DNS-01) ==="
echo "  App domain:    ${APP_DOMAIN}"
echo "  Slack domain:  ${SLACK_DOMAIN}"

cd "$PROJECT_DIR"

# Request a single certificate covering both subdomains via DNS-01 challenge
echo "Requesting certificate from Let's Encrypt..."
docker compose -f docker-compose.prod.yml run --rm certbot \
    certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/cloudflare.ini \
    -d "$APP_DOMAIN" \
    -d "$SLACK_DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --force-renewal

echo "=== SSL setup complete ==="
echo "Certificate installed for ${APP_DOMAIN} and ${SLACK_DOMAIN}"
