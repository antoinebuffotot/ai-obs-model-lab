#!/bin/bash
# Enable / disable OpenLLMetry on a running VM.
#   sudo ./set-openllmetry.sh on <tenant> <api-token>     e.g. abc12345.live.dynatrace.com dt0c01.xxx.yyy
#   sudo ./set-openllmetry.sh off
set -e
STACK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$STACK_DIR/.env"

set_kv() {
  { grep -v "^$1=" "$ENV_FILE" || true; } > "$ENV_FILE.tmp"
  echo "$1=$2" >> "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

case "${1:-}" in
  on)
    [ -n "${2:-}" ] && [ -n "${3:-}" ] || { echo "usage: $0 on <tenant> <api-token>"; exit 1; }
    set_kv OPENLLMETRY_ENABLED true
    set_kv DT_TENANT "$2"
    set_kv DT_API_TOKEN "$3"
    ;;
  off)
    set_kv OPENLLMETRY_ENABLED false
    ;;
  *)
    echo "usage: $0 on <tenant> <api-token> | off"; exit 1 ;;
esac

cd "$STACK_DIR"
# OpenInference: the collector holds the tenant and the token, restart it with the new values
if grep -q '^TELEMETRY_TYPE=openinference' "$ENV_FILE"; then docker compose --profile openinference up -d --force-recreate otel-collector; fi
docker compose up -d --force-recreate rag-api
echo "OpenLLMetry : $(grep '^OPENLLMETRY_ENABLED=' "$ENV_FILE" | cut -d= -f2)"
