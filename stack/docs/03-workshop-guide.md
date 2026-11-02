# Workshop guide: what runs on your VM

[Version française](03-workshop-guide.fr.md)

Each participant has an Ubuntu 22.04 VM of size Standard_B12ms (12 vCPU, 48 GB of memory, no GPU). All services run in Docker containers, in the /opt/ai-lab/stack folder.

## Pages and access

- `http://<vm>/`: the chat with search in documents (RAG)
- `http://<vm>/agent.html`: the AI agent, which chooses its own tools and whose every step is displayed
- `http://<vm>:8080/`: VS Code in the browser (VM password), default folder /workspace/mcp, with a Continue chat that uses the local model

## Services

- `web`: nginx, serves the pages on port 80 and relays /api calls to the chat and /agent/api to the agent
- `rag-api`: the chat's FastAPI application, which splits the documents, queries the vector database, builds the prompt and streams the response
- `agent-api`: the agent's FastAPI application (same image as rag-api), with the local tools, the Dynatrace sub-agent, the MCP tools, dtctl and the skills
- `chroma`: ChromaDB vector database, reachable only from the Docker network
- `ollama`: model server, loads qwen2.5:7b for generation and nomic-embed-text for embeddings
- `ollama-init`: one-off task that downloads the models on first startup
- `vscode`: code-server (web VS Code), with dtctl, Node.js and dt-evals

## Working folders (in VS Code, under /workspace)

- `mcp`: the mcp.json file (MCP servers) and the dtctl configuration that you create for the agent
- `skills`: the Dynatrace skills (SKILL.md files) that you choose to give to the agent
- `evals`: the dt-evals configuration used to have the model's responses scored
- `exercices`: the detailed catalog of exercises

## Useful SSH commands

- `docker compose ps` in /opt/ai-lab/stack: status of the services
- `docker compose logs -f rag-api` (or `agent-api`): application logs
- `curl localhost/api/health` and `curl localhost/agent/api/health`: status of the models, indexing, OpenLLMetry, dtctl, skills and MCP servers
- `sudo scripts/set-openllmetry.sh on <tenant> <token>`: enable OpenLLMetry on the chat (`off` to disable it)
- `sudo scripts/set-agent-openllmetry.sh on <tenant> <token>`: enable OpenLLMetry on the agent
- `sudo scripts/set-rag-context.sh on`: keep the RAG passages in the traces (required to judge the faithfulness of answers)
- `scripts/generate-traffic.sh 10`: send ten questions to produce traces
- `scripts/generate-eval-traffic.sh 2`: send a mix of questions (including out-of-document ones) to be judged by dt-evals

## Proposed exercises

The details of each exercise (objective, actions, expected results) are in the `exercices` folder in VS Code.

- **A. Discover RAG and the model**: with and without documents, add your own document, generation settings (temperature, top K, top P), system message, number of passages, limits of a local model, multilingual.
- **B. Observability with OpenLLMetry**: enable OpenLLMetry, read a chat trace, understand the exported prompt, measure with DQL, diagnose an outage.
- **C. AI agent**: first agent task, agent and documents, trace of an agent, agent settings.
- **D. External tools**: connect a Dynatrace MCP server, query Dynatrace via the sub-agent, configure dtctl, give skills to the agent, compare the access methods.
- **E. Evaluate responses with dt-evals**: prepare, run, analyze the scores, create a custom evaluator, compare two configurations.
- **F. Develop in VS Code**: modify the knowledge base, use the Continue chat, add a tool to the agent.
