#!/bin/bash
# Enable / disable OpenLLMetry (Dynatrace AI Observability) for the AGENT app on a running VM.
# The service name is ai-lab-agent-api-<vm number> (number taken from the VM host name).
#   sudo ./set-agent-openllmetry.sh on <tenant> <api-token>     e.g. abc12345.live.dynatrace.com dt0c01.xxx.yyy
#   sudo ./set-agent-openllmetry.sh off
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
    set_kv AGENT_OPENLLMETRY_ENABLED true
    set_kv DT_TENANT "$2"
    set_kv DT_API_TOKEN "$3"
    ;;
  off)
    set_kv AGENT_OPENLLMETRY_ENABLED false
    ;;
  *)
    echo "usage: $0 on <tenant> <api-token> | off"; exit 1 ;;
esac

cd "$STACK_DIR"
# OpenInference: the collector holds the tenant and the token, restart it with the new values
if grep -q '^TELEMETRY_TYPE=openinference' "$ENV_FILE"; then docker compose --profile openinference up -d --force-recreate otel-collector; fi
docker compose up -d --force-recreate agent-api
echo "Agent OpenLLMetry : $(grep '^AGENT_OPENLLMETRY_ENABLED=' "$ENV_FILE" | cut -d= -f2)"
curl -fs http://localhost/agent/api/health || true; echo
