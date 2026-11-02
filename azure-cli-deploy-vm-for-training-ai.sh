#!/bin/bash

# Lab environment for AI training
# Deploy N Ubuntu VMs (Docker + Ollama qwen2.5:7b + RAG + Web chat) on an Azure subscription.
# Menu and deployment flow inspired by https://github.com/JLLormeau/lab-environment-for-dynatrace-training

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

. ./env.sh
CONF_FILE="$SCRIPT_DIR/.lab-config"
[ -f "$CONF_FILE" ] && . "$CONF_FILE"

TIME=$(date +%Y%m%d%H%M%S)
LOG_DIR="$SCRIPT_DIR/logs/$TIME"
LOG="$SCRIPT_DIR/logs/deploy-vm-for-training-ai-$TIME.log"
APPLY="N"

###############################################################################
# helpers
###############################################################################

save_config() {
  {
    for v in DOMAIN_NAME_DEFAULT PASSWORD START_ENV NBENV OPENLLMETRY_ENABLED TELEMETRY_TYPE VM_STARTED MyTenant MyToken JUDGE_PROVIDER JUDGE_MODEL JUDGE_API_KEY; do
      printf '%s=%q\n' "$v" "${!v}"
    done
  } > "$CONF_FILE"
  chmod 600 "$CONF_FILE"
}

pause() { read -r -p "Press any key to continue " _; }

idx() { printf '%02d' "$1"; }

location_of() {
  local i=$1
  if   (( i < 5  )); then echo "$LOCATION1"
  elif (( i < 10 )); then echo "$LOCATION2"
  elif (( i < 15 )); then echo "$LOCATION3"
  else                    echo "$LOCATION4"
  fi
}

mask_token() { if [ -n "$MyToken" ]; then echo "${MyToken:0:14}***"; fi; }
mask_judge_key() { if [ -n "$JUDGE_API_KEY" ]; then echo "${JUDGE_API_KEY:0:6}***"; fi; }

valid_domain() {
  local re='^[a-z]{5}[a-z0-9]{0,40}$'
  [[ $1 =~ $re ]] && [[ ${1:0:5} != "azure" ]]
}

valid_password() {
  local v=$1 re='^[A-Za-z0-9@&#%_.+=-]+$'
  [[ ${#v} -ge 12 && ${#v} -le 72 && $v =~ $re \
     && $v == *[[:lower:]]* && $v == *[[:upper:]]* && $v == *[0-9]* && $v == *[\&\@]* ]]
}

valid_tenant() {
  local re='^[a-zA-Z0-9.-]+(/e/[a-zA-Z0-9-]+)?$'
  [[ $1 =~ $re && $1 == *.* ]]
}

valid_token() {
  local re='^dt[a-z0-9]+\.[A-Za-z0-9]+\.[A-Za-z0-9]+$'
  [[ $1 =~ $re ]]
}

print_accounts() {
  echo "#User;SSH host;Chat URL;Password"
  local i n
  for ((i=START_ENV; i<NBENV+START_ENV; ++i)); do
    n=$(idx "$i")
    echo "user$n;${DOMAIN_NAME}$n.$(location_of "$i").cloudapp.azure.com;http://${DOMAIN_NAME}$n.$(location_of "$i").cloudapp.azure.com/;$PASSWORD"
  done
}

# Build the script sent to the VM through "az vm run-command".
# Everything (config, application archive, setup script) is embedded: no dependency on a public repo.
build_setup_script() {
  local fqdn=$1 user=$2
  local otel="false" tenant="" token=""
  if [[ $OPENLLMETRY_ENABLED = [Y] ]]; then otel="true"; tenant="$MyTenant"; token="$MyToken"; fi

  echo 'mkdir -p /opt/ai-lab'
  echo "cat > /opt/ai-lab/lab.env <<'__LAB_ENV_EOF__'"
  echo "VM_FQDN='$fqdn'"
  echo "LAB_USER='$user'"
  echo "VSCODE_PASSWORD='$PASSWORD'"
  echo "JUDGE_PROVIDER='$JUDGE_PROVIDER'"
  echo "JUDGE_MODEL='$JUDGE_MODEL'"
  echo "JUDGE_API_KEY='$JUDGE_API_KEY'"
  echo "LLM_MODEL='$LLM_MODEL'"
  echo "EMBED_MODEL='$EMBED_MODEL'"
  echo "OPENLLMETRY_ENABLED='$otel'"
  echo "TELEMETRY_TYPE='$TELEMETRY_TYPE'"
  echo "DT_TENANT='$tenant'"
  echo "DT_API_TOKEN='$token'"
  echo '__LAB_ENV_EOF__'
  echo "cat > /opt/ai-lab/app.tar.gz.b64 <<'__APP_EOF__'"
  tar czf - -C "$SCRIPT_DIR" --exclude='__pycache__' --exclude='.env' stack | base64 -w 76
  echo '__APP_EOF__'
  echo "cat > /opt/ai-lab/vm-setup.sh <<'__SETUP_EOF__'"
  cat "$SCRIPT_DIR/vm-setup.sh"
  echo '__SETUP_EOF__'
  echo 'bash /opt/ai-lab/vm-setup.sh'
}

# Deploy one environment (runs in background, one log file per environment)
deploy_env() {
  local i=$1 n loc user rg tmp out
  n=$(idx "$i"); loc=$(location_of "$i"); user="user$n"; rg="${DOMAIN_NAME}${n}"

  echo "[$(date +%T)] create resource group : $rg ($loc)"
  az group create --name "$rg" --location "$loc" --tags lab="$DOMAIN_NAME" -o none || return 1

  echo "[$(date +%T)] create vm : $rg.$loc.cloudapp.azure.com ($SIZE_LINUX)"
  az deployment group create \
    --resource-group "$rg" \
    --template-file "$SCRIPT_DIR/azuredeploy-ubuntu22.json" \
    --parameters adminUsername="$user" adminPasswordOrKey="$PASSWORD" authenticationType="password" \
                 dnsNameForPublicIP="$rg" vmSize="$SIZE_LINUX" \
    -o none || return 1

  echo "[$(date +%T)] install docker + AI stack (models are pulled, this takes several minutes)"
  tmp=$(mktemp); chmod 600 "$tmp"
  build_setup_script "$rg.$loc.cloudapp.azure.com" "$user" > "$tmp"
  out=$(az vm run-command invoke -g "$rg" -n "$rg" --command-id RunShellScript \
        --scripts @"$tmp" --query 'value[0].message' -o tsv 2>&1)
  rm -f "$tmp"
  echo "$out" | tail -n 40

  if ! echo "$out" | grep -q "AI_LAB_SETUP_OK"; then
    echo "[$(date +%T)] WARNING : setup not confirmed on $rg - VM left running for investigation"
    return 2
  fi

  if [[ $VM_STARTED = [N] ]]; then
    echo "[$(date +%T)] deallocate vm $rg"
    az vm deallocate -g "$rg" -n "$rg" -o none
  fi
  echo "[$(date +%T)] DONE $rg"
}

###############################################################################
# prerequisites
###############################################################################

clear
echo "PREREQUISITE : "
echo "Each training environment is 1 Linux Ubuntu 22.04 VM with Docker :"
echo " - Size            : $SIZE_LINUX (12 vCPU / 48 GB RAM, CPU only)"
echo " - AI model        : $LLM_MODEL (+ $EMBED_MODEL for the embeddings) served by Ollama"
echo " - RAG services    : ChromaDB + RAG API (FastAPI)"
echo " - Web chat        : http://<vm>/ (port 80)"
echo " - Agentic AI      : http://<vm>/agent.html (same model, tools + step-by-step trace)"
echo " - dt-evals        : LLM judge on the traces, run from the VS Code web terminal (needs the judge key, menu 2 of the OpenLLMetry parameters)"
echo " - VS Code web     : http://<vm>:8080/ (code-server, password = the VM password)"
echo " - Observability   : OpenLLMetry (default) or OpenInference + OpenTelemetry Collector (optional, traces the prompt and the current activity only)"
echo ""
echo "A $SIZE_LINUX VM uses 12 vCPU : 5 VMs = 60 vCPU in a region (regional quota AND 'Standard BS Family' quota)."
echo "For 5 env, you need the quota of $LOCATION1"
echo "For 10 env, you need the quota of $LOCATION1 and $LOCATION2"
echo "For 15 env, you need the quota of $LOCATION1, $LOCATION2 and $LOCATION3"
echo "For 20 env, you need the quota of $LOCATION1, $LOCATION2, $LOCATION3 and $LOCATION4"
echo ""

if ! az account show >/dev/null 2>&1; then
  echo "Azure CLI is not logged in. Run 'az login' (or open Azure Cloud Shell) first."
  exit 1
fi
echo "Subscription : $(az account show --query name -o tsv)"
echo ""
for loc in "$LOCATION1" "$LOCATION2" "$LOCATION3" "$LOCATION4"; do
  echo "$loc (used, limit)"
  az vm list-usage --location "$loc" -o table 2>/dev/null | grep -E "Total Regional vCPUs|Standard BS Family vCPUs"
done
echo ""
pause

###############################################################################
# menu 1 - environments
###############################################################################

while [ "$APPLY" != "Y" ]
do
  clear
  END_ENV2=$(idx $((START_ENV+NBENV-1)))
  START_ENV2=$(idx "$START_ENV")

  echo "CONFIGURATION : "
  echo ""
  echo "Total Env (max 20) ="$NBENV
  echo " * First VM name (min 00) ="$DOMAIN_NAME_DEFAULT$START_ENV2
  echo " * Last VM name (max 19)  ="$DOMAIN_NAME_DEFAULT$END_ENV2
  echo ""
  echo "0) config env : training name ="$DOMAIN_NAME_DEFAULT
  echo "1) config env : password ="$PASSWORD
  echo "2) config env : value first env ="$START_ENV2
  echo "3) config env : nbr total env ="$NBENV
  echo "4) add env : telemetry enabled (traces sent to Dynatrace) ="$OPENLLMETRY_ENABLED
  echo "5) start env : VM started after installation ="$VM_STARTED
  echo "6) add env : telemetry type (openllmetry | openinference) ="$TELEMETRY_TYPE
  echo "A) apply and deploy the VM - (Ctrl/c to quit)"
  echo ""

  read -r -p "Input Selection (0, 1, 2, 3, 4, 5, 6 or A): " reponse

  case "$reponse" in
    "0") verif="ko"
         until [ $verif = "ok" ]; do
           read -r -p "0) config env : training name with rule [a-z]{5}[a-z0-9]+ (not starting with 'azure') " value
           if valid_domain "$value"; then verif="ok"; DOMAIN_NAME_DEFAULT=$value; save_config
           else echo "bad training name"; fi
         done
         ;;
    "1") verif="ko"
         until [ $verif = "ok" ]; do
           read -r -p "1) config env : password with 12 characters mini and 1 lower case, 1 upper case, 1 number, and @ or & " value
           if valid_password "$value"; then verif="ok"; PASSWORD=$value; save_config
           else echo "bad password (allowed characters : A-Z a-z 0-9 @ & # % _ . + = -)"; fi
         done
         ;;
    "2") value=-1
         until [[ $value =~ ^[0-9]+$ ]] && [ "$value" -ge 0 ] && [ "$value" -le $((20-NBENV)) ]; do
           read -r -p "2) config env : start value (between 0 & $((20-NBENV))) " value
         done
         START_ENV=$value; save_config
         ;;
    "3") value=-1
         until [[ $value =~ ^[0-9]+$ ]] && [ "$value" -gt 0 ] && [ "$value" -le $((20-START_ENV)) ]; do
           read -r -p "3) config env : nbr total env (maxi $((20-START_ENV))) " value
         done
         NBENV=$value; save_config
         ;;
    "4") if [ "$OPENLLMETRY_ENABLED" = "Y" ]; then OPENLLMETRY_ENABLED="N"; else OPENLLMETRY_ENABLED="Y"; fi
         echo "4) add env : telemetry enabled ="$OPENLLMETRY_ENABLED
         save_config; sleep 0.5
         ;;
    "5") if [ "$VM_STARTED" = "Y" ]; then VM_STARTED="N"; else VM_STARTED="Y"; fi
         echo "5) start env : VM started after installation ="$VM_STARTED
         save_config; sleep 0.5
         ;;
    "6") if [ "$TELEMETRY_TYPE" = "openinference" ]; then TELEMETRY_TYPE="openllmetry"; else TELEMETRY_TYPE="openinference"; fi
         echo "6) add env : telemetry type ="$TELEMETRY_TYPE
         save_config; sleep 0.5
         ;;
    "A"|"a") APPLY="Y"
         DOMAIN_NAME=$DOMAIN_NAME_DEFAULT
         ;;
  esac
done

###############################################################################
# menu 2 - Dynatrace parameters (only with the telemetry enabled)
###############################################################################

if [[ $OPENLLMETRY_ENABLED = [Y] ]]
then
  APPLY="N"
  while [ "$APPLY" != "Y" ]
  do
    echo ""
    echo "PARAMETER ($TELEMETRY_TYPE -> Dynatrace) : "
    echo ""
    echo "0) Tenant (without https://) ="$MyTenant
    if [ "$TELEMETRY_TYPE" = "openinference" ]; then
      echo "1) Token (classic dt0c01 token, scopes : openTelemetryTrace.ingest, metrics.ingest, logs.ingest) ="$(mask_token)
    else
      echo "1) Token (scope : openTelemetryTrace.ingest) ="$(mask_token)
    fi
    echo "2) LLM judge for dt-evals (optional) : provider ="$JUDGE_PROVIDER" (openai | anthropic | gemini)"
    echo "3) LLM judge for dt-evals (optional) : shared API key ="$(mask_judge_key)
    echo "A) apply and deploy the VM - (Ctrl/c to quit)"
    echo ""

    read -r -p "Input Selection (0, 1, 2, 3 or A): " reponse

    case "$reponse" in
      "0") verif="ko"
           until [ $verif = "ok" ]; do
             read -r -p "0) Tenant : <YYY>.live.dynatrace.com or <domain-name>/e/<tenant> (without https://): " value
             if valid_tenant "$value"; then verif="ok"; MyTenant=$value; save_config
             else echo "bad saas tenant address"; fi
           done
           ;;
      "1") verif="ko"
           until [ $verif = "ok" ]; do
             read -r -s -p "1) API Token : dt0c01.abcdefghij.abcdefghijklmn : " value; echo ""
             if valid_token "$value" && { [ "$TELEMETRY_TYPE" != "openinference" ] || [[ $value == dt0c01.* ]]; }; then verif="ok"; MyToken=$value; save_config
             else echo "bad API Token (OpenInference: the collector needs a classic dt0c01 token)"; fi
           done
           ;;
      "2") verif="ko"
           until [ $verif = "ok" ]; do
             read -r -p "2) Judge provider (openai | anthropic | gemini) : " value
             case "$value" in openai|anthropic|gemini) verif="ok"; JUDGE_PROVIDER=$value; save_config ;; *) echo "bad provider" ;; esac
           done
           ;;
      "3") read -r -s -p "3) Judge API key (shared with all the participants, use a budget-limited key) : " value; echo ""
           if [[ $value =~ ^[A-Za-z0-9_.-]*$ ]]; then JUDGE_API_KEY=$value; save_config
           else echo "bad key (allowed characters : A-Z a-z 0-9 _ . -)"; fi
           ;;
      "A"|"a") if [ -n "$MyTenant" ] && [ -n "$MyToken" ]; then APPLY="Y"
               else echo "Tenant and Token are required when the telemetry is enabled"; fi
           ;;
    esac
  done
fi

###############################################################################
# summary + delete script
###############################################################################

echo ""
echo "ENVIRONMENT : Linux (Ubuntu 22.04 - Docker - Ollama $LLM_MODEL - RAG - Web chat)"
print_accounts
echo ""
for loc in $(for ((i=START_ENV; i<NBENV+START_ENV; ++i)); do location_of "$i"; done | sort -u); do
  sku=$(az vm list-skus --location "$loc" --size "$SIZE_LINUX" --resource-type virtualMachines \
        --query '[?length(restrictions)==`0`].name | [0]' -o tsv 2>/dev/null)
  if [ -z "$sku" ]; then echo "WARNING : $SIZE_LINUX seems not available (or restricted) in $loc for this subscription"; fi
done
echo ""

DEL="$SCRIPT_DIR/delete_resourcegroup_${DOMAIN_NAME}_${TIME}.sh"
{
  echo "#!/bin/bash"
  echo "##Training : $DOMAIN_NAME"
  print_accounts | sed 's/^/#/'
  for ((i=START_ENV; i<NBENV+START_ENV; ++i)); do
    echo "echo ${DOMAIN_NAME}$(idx "$i")"
    echo "az group delete --name ${DOMAIN_NAME}$(idx "$i") --yes --no-wait"
  done
} > "$DEL"
chmod +x "$DEL"

pause

###############################################################################
# deployment (all environments in parallel)
###############################################################################

mkdir -p "$LOG_DIR"
{
  echo "START installation=$(date +%Y%m%d%H%M%S)"
  echo ""
  echo "##################################################################################################################################"
  if [[ $VM_STARTED = [N] ]]; then
  echo "#### Once the VMs created, they are deallocated : start them from your Azure subscription :                                  ####"
  echo "#### https://portal.azure.com/#blade/HubsExtension/BrowseResourceBlade/resourceType/Microsoft.Compute%2FVirtualMachines       ####"
  echo "#### (the AI stack restarts automatically with the VM - allow ~1 minute for the first answer, the model is loaded on demand) ####"
  echo "####                                                                                                                          ####"
  fi
  echo "#### At the end of the training, delete all the Azure resource groups :                                                       ####"
  echo "#### a script has been generated locally -> ./$(basename "$DEL")"
  echo "##################################################################################################################################"
  echo ""
} | tee -a "$LOG"

pids=(); names=()
for ((i=START_ENV; i<NBENV+START_ENV; ++i)); do
  rg="${DOMAIN_NAME}$(idx "$i")"
  deploy_env "$i" > "$LOG_DIR/$rg.log" 2>&1 &
  pids+=($!); names+=("$rg")
done
echo "${#pids[@]} environment(s) deploying in parallel - details : $LOG_DIR/<env>.log" | tee -a "$LOG"

while :; do
  alive=0
  for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=$((alive+1)); done
  [ "$alive" -eq 0 ] && break
  echo "[$(date +%T)] $alive/${#pids[@]} environment(s) still deploying..."
  sleep 30
done

failed=0
for k in "${!pids[@]}"; do
  wait "${pids[$k]}"; rc=$?
  if [ $rc -eq 0 ]; then echo "${names[$k]} : OK" | tee -a "$LOG"
  else echo "${names[$k]} : FAILED (rc=$rc) - see $LOG_DIR/${names[$k]}.log" | tee -a "$LOG"; failed=$((failed+1)); fi
done

{
  echo ""
  echo "ENVIRONMENT : Linux"
  print_accounts
  echo ""
  echo "END installation=$(date +%Y%m%d%H%M%S) (failed : $failed)"
} | tee -a "$LOG"
