#!/bin/sh
# Triggers a bulk-import run against the live app so newly posted Fort Worth
# Council agendas/minutes get pulled in without a human clicking "Import."
# years=1 keeps each run fast: the last year is more than enough to catch
# anything new, and re-scraping the full 5-year history daily would be
# wasteful (bulk-import re-fetches minutes PDFs every run, not just new ones).
set -e

TARGET_URL="${TARGET_URL:?TARGET_URL env var must be set}"

echo "Triggering bulk import at ${TARGET_URL}/bulk-import/start"
response=$(curl -sS -w "\n%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -d '{"years": 1}' \
  "${TARGET_URL}/bulk-import/start")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

echo "Response: $body"
echo "HTTP status: $http_code"

if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
  echo "Import job kicked off successfully."
  exit 0
else
  echo "Failed to trigger import job."
  exit 1
fi
