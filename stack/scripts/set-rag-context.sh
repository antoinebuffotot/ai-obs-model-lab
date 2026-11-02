#!/bin/bash
# Keep (on) or hide (off) the RAG passages in the OpenLLMetry traces of the chat and the agent.
# LLM-judge evaluations (dt-evals faithfulness / hallucination) need the retrieved context in the trace.
# The conversation history is never exported, whatever the setting.
#   sudo ./set-rag-context.sh on
#   sudo ./set-rag-context.sh off
set -e
STACK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$STACK_DIR/.env"

case "${1:-}" in
  on)  value=true ;;
  off) value=false ;;
  *)   echo "usage: $0 on | off"; exit 1 ;;
esac

{ grep -v "^OPENLLMETRY_KEEP_RAG=" "$ENV_FILE" || true; } > "$ENV_FILE.tmp"
echo "OPENLLMETRY_KEEP_RAG=$value" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

cd "$STACK_DIR"
docker compose up -d --force-recreate rag-api agent-api
echo "RAG passages in the traces : $value"
