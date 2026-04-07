#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Alfred Claude Code Container — Entrypoint
#
# Required env vars:
#   MODE          — plan | implement | review | explore
#   REPO          — GitHub repo in owner/repo format
#   GITHUB_TOKEN  — GitHub access token for cloning/pushing
#
# Mode-specific env vars:
#   TASK_DESCRIPTION  — (plan, implement, review) the coding task
#   PLAN_CONTENT      — (implement, review) the approved plan
#   BRANCH            — (implement, review) branch name
#   PR_TITLE          — (implement) pull request title
#   PR_BODY           — (implement) pull request body
#   DEFAULT_BRANCH    — (review) base branch to diff against (default: main)
#   QUESTION          — (explore) question to ask about the codebase
#   SENSITIVE_PATHS   — (implement) comma-separated paths to block in pre-commit
#
# Vertex AI auth (Claude Code uses these natively):
#   ANTHROPIC_VERTEX_PROJECT_ID
#   ANTHROPIC_VERTEX_REGION
#   GOOGLE_APPLICATION_CREDENTIALS
# ---------------------------------------------------------------------------

log() {
    echo "[alfred-claude-code] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

die() {
    log "ERROR: $*"
    exit 1
}

# --- Write GCP SA JSON to file if passed as env var ---
if [ -n "${GCP_SA_JSON:-}" ]; then
    echo "$GCP_SA_JSON" > /tmp/gcp-sa.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-sa.json
    log "Wrote GCP SA JSON to /tmp/gcp-sa.json"
fi

# --- Completion reporting trap ---
# On exit (success or failure), report completion to the backend via the
# configured method (callback, redis, or gcp_pubsub). If reporting fails,
# the polling fallback will eventually pick it up.
_report_completion() {
    local exit_code=$?
    if [ -n "${JOB_ID:-}" ] && [ -n "${COMPLETION_METHOD:-}" ]; then
        log "Reporting completion (exit_code=${exit_code}, method=${COMPLETION_METHOD})..."
        python3 /usr/local/bin/report-completion.py \
            --job-id "$JOB_ID" \
            --exit-code "$exit_code" \
            --output-dir /output \
            --method "${COMPLETION_METHOD}" \
            || log "WARNING: Completion report failed, polling fallback will handle"
    fi
}
trap _report_completion EXIT

# --- Validate required env vars ---
: "${MODE:?MODE is required (plan|implement|review|explore)}"
: "${REPO:?REPO is required (owner/repo)}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"

# --- Configure git auth ---
log "Configuring git for repo ${REPO}..."
git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
git config --global user.name "Alfred Bot"
git config --global user.email "alfred-bot@users.noreply.github.com"

# --- Clone repository ---
log "Cloning ${REPO}..."
git clone --depth=50 "https://github.com/${REPO}.git" /workspace/repo
cd /workspace/repo

# --- Mode dispatch ---
case "${MODE}" in

# ===========================================================================
# PLAN MODE
# ===========================================================================
plan)
    : "${TASK_DESCRIPTION:?TASK_DESCRIPTION is required for plan mode}"
    log "Starting plan mode..."

    claude --print --output-format json \
        "Given this repository, create a detailed implementation plan for the following task. \
Output the plan in markdown with clear numbered steps, file changes needed, and any \
considerations or risks. Be specific about what code to write and where. \
\
Task: ${TASK_DESCRIPTION}" > /output/plan.md

    log "Plan written to /output/plan.md"
    ;;

# ===========================================================================
# IMPLEMENT MODE
# ===========================================================================
implement)
    : "${TASK_DESCRIPTION:?TASK_DESCRIPTION is required for implement mode}"
    : "${PLAN_CONTENT:?PLAN_CONTENT is required for implement mode}"
    : "${BRANCH:?BRANCH is required for implement mode}"

    log "Starting implement mode on branch ${BRANCH}..."

    # Create and checkout branch
    git checkout -b "${BRANCH}"

    # Install pre-commit hook to block sensitive paths
    cp /usr/local/bin/block-sensitive-paths.sh .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    log "Installed sensitive-path pre-commit hook"

    # Write plan for Claude Code context
    printf '%s' "${PLAN_CONTENT}" > PLAN.md

    # Run Claude Code in interactive mode for implementation
    claude "Implement the following plan completely. Commit your changes with clear, \
descriptive commit messages. Do not modify any files matching sensitive path patterns \
(CI workflows, Dockerfiles, .env files, keys). \
\
Task: ${TASK_DESCRIPTION} \
\
Plan: \
${PLAN_CONTENT}"

    # Push branch
    log "Pushing branch ${BRANCH}..."
    git push origin "${BRANCH}"

    # Create draft PR
    log "Creating draft PR..."
    export GH_TOKEN="${GITHUB_TOKEN}"
    PR_URL=$(gh pr create \
        --draft \
        --title "${PR_TITLE:-${TASK_DESCRIPTION:0:72}}" \
        --body "${PR_BODY:-Automated implementation by Alfred coding assistant.}" \
        2>&1)

    PR_NUMBER=$(echo "${PR_URL}" | grep -oP '/pull/\K[0-9]+' || echo "")

    # Write result metadata
    cat > /output/result.json << EOF
{
    "pr_url": "${PR_URL}",
    "pr_number": ${PR_NUMBER:-0},
    "branch": "${BRANCH}"
}
EOF

    log "PR created: ${PR_URL}"
    ;;

# ===========================================================================
# REVIEW MODE
# ===========================================================================
review)
    : "${TASK_DESCRIPTION:?TASK_DESCRIPTION is required for review mode}"
    : "${PLAN_CONTENT:?PLAN_CONTENT is required for review mode}"
    : "${BRANCH:?BRANCH is required for review mode}"

    DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

    log "Starting adversarial review of branch ${BRANCH}..."

    # Fetch and checkout the implementation branch
    git fetch origin "${BRANCH}"
    git checkout "${BRANCH}"

    # Get the diff for context
    DIFF=$(git diff "origin/${DEFAULT_BRANCH}...HEAD")

    claude --print \
        "You are an adversarial code reviewer performing a thorough security and quality audit. \
Review the changes on branch '${BRANCH}' against the original task and plan. \
\
Structure your review with severity levels: \
- **CRITICAL**: Must fix before merge (security issues, data loss risks, broken functionality) \
- **WARNING**: Should fix (bugs, edge cases, missing validation) \
- **NOTE**: Nice to have (style, minor improvements) \
\
Check for: \
1. Correctness — Does the implementation fulfill every requirement in the task and plan? \
2. Security — Injection vulnerabilities, auth issues, exposed secrets, OWASP Top 10 \
3. Code quality — Dead code, duplication, poor naming, missing error handling at boundaries \
4. Edge cases & bugs — Off-by-one, null handling, race conditions, resource leaks \
5. Test coverage — Were tests added? Do they cover critical paths? \
6. Architecture fit — Does it follow the repo's existing patterns? \
\
Do NOT suggest new features, nice-to-have improvements, style preferences, or refactors \
outside the diff. \
\
Give a clear PASS or FAIL recommendation at the top. \
\
Task: ${TASK_DESCRIPTION} \
\
Plan: ${PLAN_CONTENT} \
\
Diff: \
${DIFF}" > /output/review.md

    log "Review written to /output/review.md"
    ;;

# ===========================================================================
# EXPLORE MODE
# ===========================================================================
explore)
    : "${QUESTION:?QUESTION is required for explore mode}"
    log "Starting explore mode..."

    claude --print "${QUESTION}" > /output/answer.md

    log "Answer written to /output/answer.md"
    ;;

*)
    die "Unknown MODE: ${MODE}. Must be one of: plan, implement, review, explore"
    ;;
esac

log "Done (mode=${MODE})"
