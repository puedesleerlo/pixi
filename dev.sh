#!/usr/bin/env bash
# Run API (8000) and web (3000) together for local development, reachable from phones on the same wifi.
set -e
cd "$(dirname "$0")"
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)
echo "PIXIE · web http://localhost:3000 · phones on this wifi: http://${LAN_IP}:3000"
( cd api && .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000 ) &
API_PID=$!
( cd web && pnpm dev --port 3000 ) &
WEB_PID=$!
trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
wait
