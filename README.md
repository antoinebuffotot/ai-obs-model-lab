# AI training environment (lab-environment-for-ai-training)

[Version française](README.fr.md)

This script quickly deploys several Ubuntu VMs with Docker on an Azure subscription, for a workshop / training course on generative AI and its observability. Each participant gets their own VM with:

- a lightweight **qwen2.5:7b** model served by Ollama (CPU only);
- a **chat web interface** (port 80) with streaming responses, clickable citations, tokens/s throughput and a settings panel (temperature, top K, top P, number of RAG passages, system message);
- **RAG services**: ChromaDB (vector database), `nomic-embed-text` embeddings, FastAPI API (indexing, search, chat);
- an **AI agent application** (page `/agent.html`) that uses the same model, calls tools and displays each step;
- a **VS Code in the browser** (port 8080) with a chat on the local model, dtctl, Node.js and dt-evals;
- optionally, **OpenLLMetry** (Traceloop SDK), which sends the chat and agent traces and metrics to Dynatrace via OTLP, for AI Observability.

Project inspired by [lab-environment-for-dynatrace-training](https://github.com/JLLormeau/lab-environment-for-dynatrace-training): same principles (Azure Cloud Shell, interactive menu, one VM per user spread over 4 regions, generated deletion script).

```
                       Azure VM Standard_B12ms (Ubuntu 22.04, 12 vCPU / 48 GB)
 browser ───80──►    ┌───────────────────────────────────────────────────────────────┐
            ──8080─► │ vscode (code-server)                                          │
                     │ web (nginx) ──► rag-api   (FastAPI, RAG chat) ──► chroma      │
                     │      └────────► agent-api (FastAPI, AI agent) ──► (vectors)   │
                     │                      │                                        │
                     │                      └──────────────► ollama                  │
                     │                                       qwen2.5:7b              │
                     │                                       nomic-embed-text        │
                     └──────────────────────────┬────────────────────────────────────┘
                                                │ OpenLLMetry (optional): OTLP/HTTPS
                                                ▼
                                       Dynatrace  /api/v2/otlp
```

The detailed documentation is in [ARCHITECTURE.md](ARCHITECTURE.md) (architecture, technologies, flows, observability, security) and in [stack/exercices/README.md](stack/exercices/README.md) (exercise catalog with objectives, actions and expected results). Each Markdown file exists in English (`*.md`, default) and in French (`*.fr.md`).

Open your Azure subscription, <https://portal.azure.com/>, then the Cloud Shell (Bash).

# Deploy the training environment

In the Cloud Shell, replace `<your-account>` with the GitHub account that hosts this repository:

```
cd;if [ -d "./lab-environment-for-ai-training" ];then rm -rf ./lab-environment-for-ai-training;fi
git clone https://github.com/antoinebuffotot/lab-environment-for-ai-training.git
cd lab-environment-for-ai-training;chmod +x ./*.sh
./azure-cli-deploy-vm-for-training-ai.sh
```

## Step 1 - 20 environments maximum

```
CONFIGURATION :

0) config env : training name =aitraining
1) config env : password =DummyP@ssword00
2) config env : value first env =00
3) config env : nbr total env =3
4) add env : OpenLLMetry enabled (traces sent to Dynatrace) =N
5) start env : VM started after installation =N
A) apply and deploy the VM - (Ctrl/c to quit)
```

| Option | Role |
|---|---|
| 0 | Training name: prefix for the VMs, resource groups and DNS (`[a-z]{5}[a-z0-9]+`, does not start with `azure`) |
| 1 | Shared password (12 characters minimum, lowercase, uppercase, digit, `@` or `&`), also used for web VS Code |
| 2 | Number of the first VM (from 00 to 19) |
| 3 | Number of VMs to create (20 maximum in total) |
| 4 | Enables OpenLLMetry: the script then asks for the Dynatrace tenant and token, then the judge LLM key (optional) |
| 5 | `Y`: the VMs stay running. `N`: they are stopped (deallocated) once installed |

The values entered are saved in `.lab-config` (ignored by git) for the next run.

The environments are deployed **in parallel** (one log per VM in `logs/<timestamp>/`). Installing a VM includes Docker, building the images and downloading the models: allow about fifteen minutes, depending on the download speed.

The VMs are spread as in the original project, 5 per region:

| VM | Region |
|---|---|
| 00 to 04 | francecentral |
| 05 to 09 | westeurope |
| 10 to 14 | northeurope |
| 15 to 19 | uksouth |

> **Quotas**: a `Standard_B12ms` uses 12 vCPUs. Five VMs in a region represent 60 vCPUs, against both the regional quota (*Total Regional vCPUs*) and the *Standard BS Family* quota. The script displays these quotas at startup and warns if the size is not available in a region. Regions are changed in `env.sh`.

## Step 2 - OpenLLMetry (option 4 = Y)

```
PARAMETER (OpenLLMetry -> Dynatrace) :

0) Tenant (without https://) =abc12345.live.dynatrace.com
1) Token (scope : openTelemetryTrace.ingest) =dt0c01.XXXXX***
2) LLM judge for dt-evals (optional) : provider =openai (openai | anthropic | gemini)
3) LLM judge for dt-evals (optional) : shared API key =sk-pro***
A) apply and deploy the VM - (Ctrl/c to quit)
```

Create a Dynatrace API token for OpenTelemetry ingestion. According to the [Dynatrace OpenLLMetry documentation](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/openllmetry), a classic token needs the scopes `openTelemetryTrace.ingest`, `metrics.ingest` and `logs.ingest` (a platform token needs the scopes `openpipeline:traces:ingest`, `openpipeline:metrics:ingest` and `openpipeline:logs:ingest`). The token is entered without echo and is only used to populate the `.env` file of the containers on each VM.

Entries 2 and 3 are optional: they define the **shared judge LLM** used by dt-evals (see `stack/evals/README.md`). The key is exposed to participants in the terminal of their web VS Code: use a key with a limited budget and revoke it after the training.

When the option is enabled, the application follows the configuration documented by Dynatrace (`Traceloop.init` to the tenant's OTLP endpoint, metrics in `delta` temporality):

- **the activity**: for the chat, `rag.chat` (workflow) with `rag.retrieve` and `rag.generate` (tasks); for the agent, `agent.run`, some `agent.step`, one span per tool and, with Dynatrace access, `ask_dynatrace` then `dynatrace_agent`;
- **the model call**: produced by the OpenLLMetry Ollama instrumentation, with the model, the settings (temperature, top K, top P), the input and output tokens and the streaming mode;
- **the exported prompt**: the user's question, the system message and the response. The conversation history and the RAG passages are sent to the model but removed from the trace before export (SDK post-processing callback). To keep the RAG passages, for example for dt-evals evaluation: `sudo stack/scripts/set-rag-context.sh on`.

Only the Ollama instrumentation is active (ChromaDB and HTTP are excluded). The Dynatrace services are named `ai-lab-rag-api-<VM number>` (chat) and `ai-lab-agent-api-<VM number>` (agent), with the `host.name` attribute carrying the VM's FQDN.

The traces contain the text of the questions and responses: only enable the option with a tenant where this content may be stored. To stop tracing any prompt or response text, set `OPENLLMETRY_TRACE_CONTENT=false` in `stack/.env`.

## Training applications and tools

### AI agent (page `/agent.html`)

A second page, with the same interface (languages, settings, Observability tab), provides an **agentic application** that uses the same local model as the chat. The agent decides on its own to call tools (`search_documents`, `list_documents`, `calculator`, `get_current_time`), reads the results and starts again until it can answer (limited number of steps). Each step and each tool call is displayed.

- Docker service `agent-api` (same image as `rag-api`, code in `stack/rag-api/app/agent.py` and `agent_main.py`), reached through nginx on `/agent/api/`.
- OpenLLMetry follows `OPENLLMETRY_ENABLED` by default; to enable or disable it on the agent alone: `sudo stack/scripts/set-agent-openllmetry.sh on <tenant> <token>` / `off`.
- Traces: `agent.run` (@agent) > `agent.step` (@task) > Ollama LLM call, plus one span per tool (@tool).

### Dynatrace sub-agent, MCP, dtctl and skills

- **Dynatrace sub-agent**: when Dynatrace access exists (MCP server declared or dtctl configured), the main agent only receives one tool, `ask_dynatrace`. It delegates to a specialized sub-agent (its own instruction and context, only the Dynatrace tools) that queries the platform and returns a short summary. The sub-agent's activity is displayed in the tool's card. Traces: `agent.run` > `ask_dynatrace` (@tool) > `dynatrace_agent` (@agent) > LLM steps and one span per tool call. `MCP_SUBAGENT=false` gives the tools directly to the main agent; `DT_AGENT_MAX_STEPS` limits the sub-agent's steps (4 by default).
- **MCP tools (participant exercise)**: the agent reads the `mcp.json` file that participants create themselves in web VS Code (folder `/workspace/mcp` = `stack/mcp`, see `stack/mcp/README.md` and `mcp.json.example`) to connect to a remote MCP server, for example the Dynatrace MCP server. Automatic reload, no restart.
- **dtctl and skills (participant exercises)**: the sub-agent can also use `dtctl` (Dynatrace CLI, read-only: list of allowed commands, no `config`/`apply`/`delete`...) that participants configure in the web VS Code terminal (`stack/mcp/README.md`), and Dynatrace *skills* (`SKILL.md` from <https://github.com/Dynatrace/dynatrace-for-ai>) that they copy into `stack/skills/` (`stack/skills/README.md`). The agent sees the short list of skills and reads a skill with `read_skill` on demand. The state (dtctl, skills) is displayed in the Tools tab of the agent page.

### Evaluating responses with dt-evals (participant exercise)

Participants judge the model's responses with [dt-evals](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/llm-judge-evaluation) (LLM-as-a-judge on traces) from the web VS Code terminal (Node and dt-evals are in the image; folder `stack/evals/`, see `stack/evals/README.md`). The judge is an external model: the trainer provides **a shared key** (step 2 of the deployment: provider `openai|anthropic|gemini` and key, exposed in the terminal under the provider's variable name). `stack/scripts/generate-eval-traffic.sh` produces varied responses (including out-of-document ones) and `stack/scripts/set-rag-context.sh on|off` keeps the RAG passages in the traces (needed to judge faithfulness to the sources).

## Chat settings

The **Settings** tab of the web interface adjusts, for the next question:

| Setting | Range | Default | Effect |
|---|---|---|---|
| Temperature | 0 to 2 | 0.3 | Low: stable responses. High: more varied responses |
| Top K | 1 to 100 | 40 | Number of candidate tokens examined at each step |
| Top P | 0 to 1 | 0.9 | Maximum cumulative probability of the candidates kept |
| Document passages | 1 to 8 | 3 | Number of RAG passages added to the prompt |
| System message | free text | workshop message, in the chosen language | Role and tone of the model. The default text follows the interface language as long as it has not been modified |

The settings are saved in the browser, and the "Restore default values" button resets them. The throughput and the settings used are displayed under each response, which makes comparison possible. The conversation is kept when switching from the Chat page to the Agent page and vice versa.

**Enable or disable OpenLLMetry afterwards**, over SSH on the VM:

```
cd /opt/ai-lab/stack
sudo scripts/set-openllmetry.sh on <tenant> <token>
sudo scripts/set-openllmetry.sh off
```

**Choose the telemetry type** (OpenLLMetry by default, or OpenInference through an OpenTelemetry Collector; it needs a classic `dt0c01` token):

```
sudo scripts/set-telemetry-type.sh openinference
sudo scripts/set-telemetry-type.sh openllmetry
```

## List of created environments

```
ENVIRONMENT : Linux
#User;SSH host;Chat URL;Password
user00;aitraining00.francecentral.cloudapp.azure.com;http://aitraining00.francecentral.cloudapp.azure.com/;DummyP@ssword00
user01;aitraining01.francecentral.cloudapp.azure.com;http://aitraining01.francecentral.cloudapp.azure.com/;DummyP@ssword00
user02;aitraining02.francecentral.cloudapp.azure.com;http://aitraining02.francecentral.cloudapp.azure.com/;DummyP@ssword00
```

## Access - example for user00 with the training name `aitraining`

| Service | Access |
|---|---|
| Web chat | `http://aitraining00.francecentral.cloudapp.azure.com/` |
| AI agent | `http://aitraining00.francecentral.cloudapp.azure.com/agent.html` |
| Web VS Code | `http://aitraining00.francecentral.cloudapp.azure.com:8080/` (VM password) |
| SSH | `ssh user00@aitraining00.francecentral.cloudapp.azure.com` |
| Chat API (via nginx) | `http://aitraining00.francecentral.cloudapp.azure.com/api/health` |
| Agent API (via nginx) | `http://aitraining00.francecentral.cloudapp.azure.com/agent/api/health` |

Only ports 22, 80 and 8080 (web VS Code, protected by the VM password) are open. Ollama and ChromaDB are only reachable from the VM's Docker network: to query them directly (for example `curl` on the Ollama API), publish their port in `stack/docker-compose.yml` on `127.0.0.1` and go through an SSH tunnel.

If option 5 is `N`, start the VMs from the Azure portal before the training. The stack restarts by itself (`restart: unless-stopped`); the first response is slower because the model is reloaded into memory.

## On the VM

```
cd /opt/ai-lab/stack
docker compose ps                    # service status
docker compose logs -f rag-api       # chat API logs (agent-api for the agent)
curl localhost/api/health            # models ready, documents indexed, OpenLLMetry active or not
curl localhost/agent/api/health      # same for the agent, with dtctl, skills and MCP servers
scripts/generate-traffic.sh 10       # 10 questions to produce traces
sudo tail -f /var/log/ai-lab-setup.log   # installation log
```

## Chat API (RAG)

| Method | Route | Role |
|---|---|---|
| GET | `/api/health` | State of the models, indexing, OpenLLMetry and service name |
| GET | `/api/settings` | Default chat settings and default system messages (per language) |
| POST | `/api/chat` | Question, history and settings (`temperature`, `top_k`, `top_p`, `passages`, `system_prompt`), SSE streaming response (`sources`, `token`, `done`, `error`) |
| POST | `/api/search` | Vector search only, without generation (fields `query`, `passages`) |
| GET / DELETE | `/api/documents` | List and deletion of indexed documents |
| POST | `/api/upload` | Add a document (.txt, .md, .pdf, 5 MB maximum) |
| POST | `/api/ingest` | Reindexing of the sample documents (`stack/docs/`) |
| GET | `/api/observability/code` | OpenLLMetry configuration code (Observability tab) |

The agent API (`/agent/api/…`) exposes `health`, `settings`, `tools`, `observability/code` and `chat` (SSE streaming: `step`, `token`, `tool_call`, `tool_result`, `warning`, `done`, `error`).

Example:

```
curl -sN localhost/api/chat -H 'Content-Type: application/json' \
     -d '{"message":"C'"'"'est quoi OpenLLMetry ?","use_rag":true}'
```

To change the base content of the workshop, add `.md`, `.txt` or `.pdf` files in `stack/docs/` before deployment: they are indexed on the first start of each VM (on an existing VM, use "Reindex the samples"). Only the English files (`*.md`) are indexed by default; the `*.fr.md` files are indexed only when `DOCS_LANG=fr` (they then replace the English versions).

## Performance and costs

- The model runs **without a GPU**: expect a few tokens per second. The interface displays the actual throughput of each response, which also serves as a teaching aid.
- The first question after a start is longer (loading the model into memory). An agent chains several model calls: a task with several tools can take several minutes.
- A `Standard_B12ms` is an expensive VM: stop them (option 5 = `N`, or from the portal) between two sessions and delete them at the end of the training.
- To change the model, modify `LLM_MODEL` in `env.sh` (for example another model from the Ollama library). The default system messages are in `stack/rag-api/app/rag.py` (chat) and `agent.py` (agent).

## Last step - Delete the resource groups

At the end, use the script generated in the project directory to clean up the subscription:

```
./delete_resourcegroup_aitraining_<timestamp>.sh
```

It deletes the created resource groups (`az group delete --no-wait`) and contains the list of accounts as a comment.

## Repository structure

```
azure-cli-deploy-vm-for-training-ai.sh   main script and menu
azuredeploy-ubuntu22.json                ARM template (VM, static public IP + DNS, NSG 22/80/8080)
vm-setup.sh                              installation on the VM (Docker, AI stack), run via az vm run-command
env.sh                                   VM size, regions, models, default values
ARCHITECTURE.md  README.md               documentation (English: *.md, French: *.fr.md)
stack/
  docker-compose.yml                     ollama, ollama-init, chroma, rag-api, agent-api, web, vscode
  nginx.conf                             reverse proxy (SSE streaming)
  web/                                   index.html (chat), agent.html (agent), common.css, common.js
  rag-api/                               shared Python image: RAG chat, agent, MCP, dtctl, skills, OpenLLMetry
  vscode/                                code-server (Continue, dtctl, Node.js, dt-evals)
  docs/                                  sample documents indexed at startup (only the English *.md files are indexed by default, see DOCS_LANG)
  mcp/  skills/  evals/                  workspaces for the participant exercises
  exercices/                             exercise catalog
  scripts/                               OpenLLMetry scripts (chat, agent), RAG context, traffic generation
```

The `stack/` folder is embedded in the script sent to each VM: the repository can therefore be private and your local changes are picked up at the next deployment.

## Troubleshooting

| Symptom | Lead |
|---|---|
| `QuotaExceeded` / `SkuNotAvailable` | Insufficient vCPU quota or `Standard_B12ms` unavailable in the region: change the regions in `env.sh` or request a quota increase |
| Environment `FAILED` or `setup not confirmed` | Read `logs/<timestamp>/<env>.log`, then `/var/log/ai-lab-setup.log` on the VM (the VM is left running in this case) |
| The chat displays "the model is downloading" | The download is not finished: `docker compose logs ollama-init` |
| No traces in Dynatrace | `curl localhost/api/health` must return `"openllmetry":true`; otherwise check the tenant and token (`docker compose logs rag-api`) |
| The agent page displays "Service unreachable" or `502` | `agent-api` is not started: `docker compose up -d agent-api web`, then `docker compose logs agent-api` |
| The agent does not use the MCP tools | `curl localhost/agent/api/health`: read the state of each server in `mcp` (401: token; 403: `mcp-gateway:*` permissions; otherwise network); limit the tools with `"tools"` in `mcp.json` |
| Truncated agent responses | Context window full: orange alert in the page; increase `AGENT_NUM_CTX` or reduce the tools |
| dtctl chip red on the agent page | dtctl is not in the image of the `agent-api` service (installing dtctl in the VS Code terminal only affects the VS Code container). Rebuild: `docker compose build --no-cache agent-api vscode && docker compose up -d`, then look for `dtctl ... installed` or `WARNING` in the build output; check with `docker compose exec agent-api dtctl --help`. Orange = installed but `dtctl-config` is missing |
| The agent reports only part of a list (e.g. 1 problem out of 4) | Look at the tool card in the page: if the result contains all the items, it is the model summarizing badly (ask for the full list, use fewer MCP tools); if it ends with `result truncated`, the tool result exceeded `TOOL_RESULT_CHARS` (6000 by default): raise it in `stack/.env` (and `AGENT_NUM_CTX`), or ask a narrower question |
