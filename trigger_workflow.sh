#!/bin/bash
# Triggers the literature_bot GitHub Actions workflow
# Called by launchd every Monday at 08:00

REPO="RijndertAriese/literature_bot"
WORKFLOW="digest.yml"
TOKEN_FILE="$(dirname "$0")/.github_token"
LOG_FILE="$(dirname "$0")/trigger_workflow.log"

TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')
if [ -z "$TOKEN" ]; then
  echo "$(date): ERROR - token file not found or empty" >> "$LOG_FILE"
  exit 1
fi

HTTP_CODE=$(curl -s -o /tmp/gh_dispatch_response.txt -w "%{http_code}" \
  -X POST \
  -H "Authorization: token $TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
  -d '{"ref":"main"}')

RESPONSE=$(cat /tmp/gh_dispatch_response.txt)

if [ "$HTTP_CODE" = "204" ]; then
  echo "$(date): SUCCESS - workflow triggered (HTTP $HTTP_CODE)" >> "$LOG_FILE"
elif [ "$HTTP_CODE" = "401" ]; then
  echo "$(date): ERROR - token invalid or expired (HTTP $HTTP_CODE)" >> "$LOG_FILE"
elif [ "$HTTP_CODE" = "404" ]; then
  echo "$(date): ERROR - repo or workflow not found (HTTP $HTTP_CODE)" >> "$LOG_FILE"
else
  echo "$(date): ERROR - unexpected response (HTTP $HTTP_CODE): $RESPONSE" >> "$LOG_FILE"
fi
