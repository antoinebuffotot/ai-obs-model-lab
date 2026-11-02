#!/bin/bash
# Send a few questions to the chat API (useful to fill Dynatrace with traces).
#   ./generate-traffic.sh [count] [base_url]
COUNT=${1:-10}
URL=${2:-http://localhost}
QUESTIONS=(
  "C'est quoi OpenLLMetry ?"
  "Explique le principe du RAG en trois etapes"
  "Quels services tournent sur cette VM ?"
  "Pourquoi decouper les documents en passages ?"
  "Quelles informations contient une trace LLM ?"
)
for ((i=0; i<COUNT; i++)); do
  q=${QUESTIONS[$((RANDOM % ${#QUESTIONS[@]}))]}
  echo "[$((i+1))/$COUNT] $q"
  curl -sN -X POST "$URL/api/chat" -H 'Content-Type: application/json' \
       -d "{\"message\":\"$q\",\"use_rag\":true}" > /dev/null
done
