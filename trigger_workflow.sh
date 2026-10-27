#!/bin/bash
# Triggers the LiteratureDigest GitHub Actions workflow (optional backup for the
# workflow's own cron schedule). Can be run by launchd every Monday at 08:00.
#
# Uses the GitHub CLI, which keeps its credentials in the macOS Keychain, so no
# token file is needed. One-time setup: `gh auth login`.

REPO="RijndertAriese/LiteratureDigest"
WORKFLOW="digest.yml"
LOG_FILE="$(dirname "$0")/trigger_workflow.log"

# launchd starts with a minimal PATH; look in the usual Homebrew locations too.
GH="$(command -v gh || ls /opt/homebrew/bin/gh /usr/local/bin/gh 2>/dev/null | head -n 1)"
if [ -z "$GH" ]; then
  echo "$(date): ERROR - GitHub CLI (gh) not found" >> "$LOG_FILE"
  exit 1
fi

if OUTPUT=$("$GH" workflow run "$WORKFLOW" --repo "$REPO" --ref main 2>&1); then
  echo "$(date): SUCCESS - workflow triggered" >> "$LOG_FILE"
else
  echo "$(date): ERROR - $OUTPUT" >> "$LOG_FILE"
  exit 1
fi
