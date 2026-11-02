#!/bin/bash
# Choose the telemetry type of the chat and the agent on a running VM (the on/off switch stays set-openllmetry.sh).
#   sudo ./set-telemetry-type.sh openllmetry     Traceloop SDK -> Dynatrace (default)
#   sudo ./set-telemetry-type.sh openinference   OpenInference -> OpenTelemetry Collector (container otel-collector) -> Dynatrace
# OpenInference needs a classic API token (dt0c01.*) with openTelemetryTrace.ingest, metrics.ingest and logs.ingest.
set -e
STACK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$STACK_DIR/.env"

set_kv() {
  { grep -v "^$1=" "$ENV_FILE" || true; } > "$ENV_FILE.tmp"
  echo "$1=$2" >> "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

cd "$STACK_DIR"
case "${1:-}" in
  openllmetry)
    set_kv TELEMETRY_TYPE openllmetry
    set_kv COMPOSE_PROFILES ""
    docker compose --profile openinference stop otel-collector 2>/dev/null || true
    docker compose --profile openinference rm -f otel-collector 2>/dev/null || true
    ;;
  openinference)
    if grep -q '^DT_API_TOKEN=' "$ENV_FILE" && ! grep -q '^DT_API_TOKEN=dt0c01\.' "$ENV_FILE"; then
      echo "warning: the collector sends DT_API_TOKEN as 'Api-Token', use a classic token (dt0c01.*)"
    fi
    set_kv TELEMETRY_TYPE openinference
    set_kv COMPOSE_PROFILES openinference
    docker compose --profile openinference up -d --force-recreate otel-collector
    ;;
  *)
    echo "usage: $0 openllmetry | openinference"; exit 1 ;;
esac

docker compose up -d --force-recreate rag-api agent-api
echo "Telemetry type : $(grep '^TELEMETRY_TYPE=' "$ENV_FILE" | cut -d= -f2)  (enabled : $(grep '^OPENLLMETRY_ENABLED=' "$ENV_FILE" | cut -d= -f2))"
