#!/bin/bash
# Teardown a worktree and its database
# Usage: ./scripts/cleanup-worktree.sh
# Run from the worktree root

set -e

DB_NAME="alfred_$(basename $PWD)"
WORKTREE_NAME=$(basename $PWD)
MAIN_REPO="$(git rev-parse --show-toplevel)"
COMPOSE_FILE="$MAIN_REPO/docker-compose.dev.yml"

echo "Cleaning up worktree: $WORKTREE_NAME"
echo "Database: $DB_NAME"

# Drop database
echo "Dropping database..."
docker-compose -f "$COMPOSE_FILE" exec -T postgres psql -U alfred -c "DROP DATABASE IF EXISTS $DB_NAME;"

# Remove worktree
echo "Removing worktree..."
cd "$MAIN_REPO"
git worktree remove ".worktrees/$WORKTREE_NAME" 2>/dev/null || echo "Worktree already removed"

# Delete branch (optional - uncomment if desired)
# git branch -D "$WORKTREE_NAME" 2>/dev/null || echo "Branch not deleted (may have unmerged changes)"

echo "Cleanup complete!"
