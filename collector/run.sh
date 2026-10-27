#!/bin/sh
set -eu

socket=/run/shc-monitor/collector.sock
rm -f "$socket"

/opt/shc-monitor/collector/.venv/bin/uvicorn app.main:app \
  --app-dir /opt/shc-monitor/collector \
  --uds "$socket" \
  --no-access-log &
server_pid=$!

terminate() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap terminate INT TERM EXIT

attempt=0
while [ ! -S "$socket" ]; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    wait "$server_pid"
    exit 1
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 600 ]; then
    echo "collector socket was not created" >&2
    exit 1
  fi
  sleep 0.05
done

chmod 0660 "$socket"
wait "$server_pid"

