#!/bin/bash
# Send a mix of questions to the chat API to give dt-evals something to judge: answers grounded in the documents,
# questions the documents cannot answer (hallucination bait), questions in other languages, with and without RAG.
#   ./generate-eval-traffic.sh [rounds] [base_url]
# On the VM: base_url http://localhost (default). From the VS Code web terminal: http://web
ROUNDS=${1:-1}
URL=${2:-http://localhost}

# "rag|question"
QUESTIONS=(
  "true|C'est quoi OpenLLMetry ?"
  "true|Explique le principe du RAG en trois étapes"
  "true|Quels services tournent sur cette VM ?"
  "true|Que contient exactement le document 99 sur Kubernetes ?"
  "true|Quelle est la capitale de l'Australie ?"
  "true|What does the workshop send to Dynatrace as traces?"
  "true|¿Qué es el RAG y para qué sirve en este taller?"
  "false|C'est quoi OpenLLMetry ?"
  "false|Quelle est la température d'ébullition de l'eau au sommet de l'Everest ?"
  "false|Donne-moi la liste des modèles installés sur cette VM."
)

n=0
for ((r=1; r<=ROUNDS; r++)); do
  for item in "${QUESTIONS[@]}"; do
    rag=${item%%|*}; q=${item#*|}; n=$((n+1))
    echo "[$n] rag=$rag  $q"
    body=$(printf '{"message":"%s","use_rag":%s}' "${q//\"/\\\"}" "$rag")
    curl -sN -X POST "$URL/api/chat" -H 'Content-Type: application/json' -d "$body" > /dev/null
  done
done
echo "Done: $n questions sent. Wait a minute for the traces to reach Dynatrace, then run dt-evals."
