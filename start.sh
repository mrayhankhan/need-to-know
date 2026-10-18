#!/bin/sh
# Start FalkorDB (Redis + module) in the background, wait for it, then serve the app.
set -e
MODULE="$(cat /app/.falkordb_module)"
REDIS="$(cat /app/.redis_server)"
"$REDIS" --port 6379 --bind 127.0.0.1 --dir /data --save "" --loadmodule "$MODULE" --daemonize yes
i=0
until python -c "import socket; socket.create_connection(('127.0.0.1', 6379), 1)" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -gt 50 ] && echo "FalkorDB did not start" && exit 1; sleep 0.2
done
python -m ntk.seed
exec uvicorn ntk.api:app --host 0.0.0.0 --port "${PORT:-7860}"
