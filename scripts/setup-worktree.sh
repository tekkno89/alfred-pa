#!/bin/bash
# Setup a new worktree with its own database
# Usage: ./scripts/setup-worktree.sh
# Run from the worktree root after creating it

set -e

DB_NAME="alfred_$(basename $PWD)"
COMPOSE_FILE="$(git rev-parse --show-toplevel)/docker-compose.dev.yml"

echo "Setting up worktree: $(basename $PWD)"
echo "Database: $DB_NAME"

# Create database (ignore error if exists)
docker-compose -f "$COMPOSE_FILE" exec -T postgres psql -U alfred -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || echo "Database already exists"

# Run migrations locally (not in Docker - worktree has different code)
echo "Running migrations..."
cd backend
DATABASE_URL="postgresql+asyncpg://alfred:alfred@localhost:5432/$DB_NAME" JWT_SECRET=dev-secret uv run alembic upgrade head
cd ..

echo ""
echo "Worktree setup complete!"
echo "Database: $DB_NAME"
echo ""
echo "Next steps:"
echo "  1. If using direnv: direnv allow"
echo "  2. Run tests: cd backend && uv run pytest"
