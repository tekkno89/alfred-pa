#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

# Read domains from .env
APP_DOMAIN=$(grep -E '^APP_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)
SLACK_DOMAIN=$(grep -E '^SLACK_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$APP_DOMAIN" || -z "$SLACK_DOMAIN" ]]; then
    echo "ERROR: APP_DOMAIN and SLACK_DOMAIN must be set in .env"
    exit 1
fi

EMAIL=$(grep -E '^CERTBOT_EMAIL=' "$ENV_FILE" | cut -d= -f2- 2>/dev/null || echo "admin@${APP_DOMAIN}")

echo "=== SSL Certificate Setup ==="
echo "  App domain:   ${APP_DOMAIN}"
echo "  Slack domain:  ${SLACK_DOMAIN}"

cd "$PROJECT_DIR"

# Start only the frontend on port 80 for ACME challenge
echo "Starting frontend for ACME challenge..."
docker compose -f docker-compose.prod.yml up -d frontend

echo "Waiting for port 80 to be ready..."
sleep 5

# Request a single certificate covering both subdomains
echo "Requesting certificate from Let's Encrypt..."
docker compose -f docker-compose.prod.yml run --rm certbot \
    certonly \
    --webroot \
    -w /var/www/certbot \
    -d "$APP_DOMAIN" \
    -d "$SLACK_DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --force-renewal

echo "Restarting frontend to load SSL certificate..."
docker compose -f docker-compose.prod.yml restart frontend

echo "=== SSL setup complete ==="
echo "Certificate installed for ${APP_DOMAIN} and ${SLACK_DOMAIN}"
