#!/bin/bash
# Executed as root on each VM (through "az vm run-command").
# Installs Docker, deploys the AI stack (Ollama + ChromaDB + RAG API + Web chat)
# and waits until the models are pulled and the sample documents are indexed.

set -u
export DEBIAN_FRONTEND=noninteractive
export HOME="${HOME:-/root}"
LAB_DIR=/opt/ai-lab
LOG=/var/log/ai-lab-setup.log
exec > >(tee -a "$LOG") 2>&1

. "$LAB_DIR/lab.env"
echo "== AI lab setup start $(date -u +%FT%TZ) on $VM_FQDN"

# wait for the first-boot apt activity
cloud-init status --wait >/dev/null 2>&1 || true

# Docker engine + compose plugin
if ! command -v docker >/dev/null 2>&1; then
  for attempt in 1 2 3; do
    curl -fsSL https://get.docker.com | sh && break
    echo "docker install failed (attempt $attempt), retrying..."; sleep 15
  done
fi
systemctl enable --now docker
if ! docker compose version >/dev/null 2>&1; then
  apt-get update -y && apt-get install -y docker-compose-plugin
fi
usermod -aG docker "$LAB_USER" 2>/dev/null || true

# Application files (shipped in the run-command script)
base64 -d "$LAB_DIR/app.tar.gz.b64" | tar xz -C "$LAB_DIR"
cd "$LAB_DIR/stack" || exit 1

cat > .env <<EOF
LLM_MODEL=$LLM_MODEL
EMBED_MODEL=$EMBED_MODEL
VM_FQDN=$VM_FQDN
OPENLLMETRY_ENABLED=$OPENLLMETRY_ENABLED
TELEMETRY_TYPE=${TELEMETRY_TYPE:-openllmetry}
COMPOSE_PROFILES=$([ "${TELEMETRY_TYPE:-openllmetry}" = openinference ] && echo openinference)
DT_TENANT=$DT_TENANT
DT_API_TOKEN=$DT_API_TOKEN
OTEL_SERVICE_NAME=ai-lab-rag-api
VSCODE_PASSWORD=$VSCODE_PASSWORD
JUDGE_PROVIDER=${JUDGE_PROVIDER:-openai}
JUDGE_MODEL=${JUDGE_MODEL:-}
JUDGE_API_KEY=${JUDGE_API_KEY:-}
EOF
chmod 600 .env
chmod +x scripts/*.sh

docker compose up -d --build

# Wait until models are pulled and documents indexed (max 40 minutes)
ready=0
for i in $(seq 1 480); do
  if curl -fs http://localhost/api/health 2>/dev/null | grep -q '"ready":true'; then ready=1; break; fi
  sleep 5
done

docker compose ps
if [ "$ready" = "1" ]; then
  echo "AI_LAB_SETUP_OK"
  echo "Chat : http://$VM_FQDN/"
else
  echo "AI_LAB_SETUP_TIMEOUT - check: docker compose -f $LAB_DIR/stack/docker-compose.yml logs"
fi
