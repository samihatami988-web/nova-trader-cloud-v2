#!/usr/bin/env sh
set -e
BASE="${1:-http://127.0.0.1:8000}"
echo "Health:"
curl -fsS "$BASE/health"
echo "\n\nAuth check (set NOVA_KEY first):"
if [ -n "$NOVA_KEY" ]; then
  curl -fsS -H "X-NOVA-Key: $NOVA_KEY" "$BASE/api/auth-check"
  echo "\n\nUniverse:"
  curl -fsS -H "X-NOVA-Key: $NOVA_KEY" "$BASE/api/universe"
else
  echo "NOVA_KEY not set; skipped authenticated checks."
fi
