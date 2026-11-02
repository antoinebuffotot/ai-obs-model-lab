# Exercise catalog

[Version française](README.fr.md)

Six blocks, from simplest to most advanced. Each exercise states the objective, the participant's actions and the expected result,
in the web application and/or in Dynatrace. The detailed guides for exercises D (MCP, dtctl, skills) and E (dt-evals) are in
`/workspace/mcp/README.md`, `/workspace/skills/README.md` and `/workspace/evals/README.md`.

**Common prerequisites.** OpenLLMetry is active on the VM for blocks B to E. Dynatrace access (ingest token, platform
tokens) is provided or created by the participants depending on the exercise. In the VS Code web terminal, the chat is reachable
at `http://web`.

**Suggested schedule (one day).** Morning: A (45 min), B1 to B4 (60 min), C (45 min). Afternoon: D1 to D3 or D4 (60 to 90 min),
E1 to E4 (60 min), then B5, D6 or F for the faster participants.

---

## Block A. Discover RAG and the model (without Dynatrace)

### A1. RAG with and without documents
- **Objective**: understand what RAG brings.
- **Actions**: ask the same question with "Search in documents" checked, then unchecked.
- **Expected result**: *Web*: with RAG, the answer cites numbered passages (`[1]`) and displays "Passages used" with a relevance
  score; without RAG, no sources and more general answers.

### A2. Add your own document
- **Objective**: see indexing in action.
- **Actions**: Documents tab, "Add a document" (`.txt`, `.md`, `.pdf`), ask a question about its content; remove it
  and ask the question again.
- **Expected result**: *Web*: the number of indexed passages is displayed, the answer cites the new document, then no longer cites it after removal.

### A3. Generation parameters
- **Objective**: understand temperature, top K and top P.
- **Actions**: Settings tab, ask the same question 3 times with very different values.
- **Expected result**: *Web*: more stable or more varied answers; the settings line under each answer lets you compare.

### A4. System message
- **Objective**: steer the model's behavior.
- **Actions**: edit the system message ("answer in one sentence", change the tone), change the interface language,
  restore the default values.
- **Expected result**: *Web*: answer style changed. The default text switches to the chosen language as long as it has not been edited;
  an edited text is kept.

### A5. Number of passages and relevance
- **Objective**: measure the trade-off between context and latency.
- **Actions**: vary "Document passages" from 1 to 8; click the `[n]` markers to open the passages.
- **Expected result**: *Web*: more context but a slower answer with 8 passages; each citation opens and highlights its passage.

### A6. Limits of a local model on CPU
- **Objective**: get a sense of the performance of a small model without a GPU.
- **Actions**: ask a question outside the documents, read the displayed throughput.
- **Expected result**: *Web*: tokens per second and total time; the model states that the answer does not come from the documents.

### A7. Multilingual
- **Objective**: check that the model follows the language of the question.
- **Actions**: choose one of the 5 languages, ask a question in another language, switch from the Chat page to the Agent page.
- **Expected result**: *Web*: answer in the language of the question; the conversation is restored when returning to the page.

---

## Block B. Observability with OpenLLMetry

### B1. Enable OpenLLMetry
- **Objective**: connect the application to Dynatrace.
- **Actions**: over SSH, `sudo scripts/set-openllmetry.sh on <tenant> <token>`, then ask a question.
- **Expected result**: *Web*: "OpenLLMetry: active" badge. *Dynatrace*: a service `ai-lab-rag-api-NN` (NN = VM number).
  The Observability tab of the web page shows the configuration code.

### B2. Read a chat trace
- **Objective**: follow the steps of a question.
- **Actions**: open the trace of a question in Distributed Tracing or AI Observability.
- **Expected result**: *Dynatrace*: `rag.chat` contains `rag.retrieve` (with the embedding call) and `rag.generate` (with the model call).
  The model span carries the model name, temperature, top K, tokens and streaming mode.

### B3. What the trace shows of the prompt
- **Objective**: discuss prompt confidentiality.
- **Actions**: read the inputs of the model span and compare them with what the model actually received.
- **Expected result**: *Dynatrace*: the question, the system message and the answer are visible; neither the history nor the RAG passages.
  The number of input tokens is larger than the visible prompt: to be explained.

### B4. Impact of settings on the trace
- **Objective**: relate settings, duration and tokens.
- **Actions**: change temperature, top K and number of passages, ask questions, compare the spans.
- **Expected result**: *Dynatrace*: the request attributes change and the duration of `rag.generate` varies with the number of tokens.

### B5. Measure with DQL
- **Objective**: use traces as data.
- **Actions**: generate traffic (`scripts/generate-traffic.sh 10`), write DQL queries on the spans of your service (latency per
  step, tokens per minute) and pin them to a dashboard.
- **Expected result**: *Dynatrace*: a personal dashboard with latency, tokens and volume.

### B6. Cause and diagnose an outage *(to be verified on a real tenant)*
- **Objective**: recognize a failure in the telemetry.
- **Actions**: over SSH, `docker compose stop ollama`, ask a question, then `docker compose start ollama`.
- **Expected result**: *Web*: error message or "Service unreachable". *Dynatrace*: a span in error, with the exception probably visible.

---

## Block C. AI agent (page `/agent.html`)

### C1. First agent task
- **Objective**: see a tool loop.
- **Actions**: task "Calculate (1250 * 1.2) + 340, then give the current date and time".
- **Expected result**: *Web*: each step, the calls to `calculator` and `get_current_time` with their results, then the final answer.

### C2. Agent and documents
- **Objective**: compare an agent and a RAG chat.
- **Actions**: task "Which documents are available, and what does the one about OpenLLMetry say?", then the same question in the chat.
- **Expected result**: *Web*: the agent calls `list_documents` then `search_documents`, whereas the chat does a single search.

### C3. Enable OpenLLMetry on the agent and read its trace
- **Objective**: observe an agent.
- **Actions**: `sudo scripts/set-agent-openllmetry.sh on <tenant> <token>`, run C1 and C2, open the traces.
- **Expected result**: *Dynatrace*: a service `ai-lab-agent-api-NN` with `agent.run`, `agent.step` spans (one model call each) and a
  span per tool. There are more model calls than for the chat.

### C4. Tune the agent
- **Objective**: understand the guardrails.
- **Actions**: reduce "Maximum steps" to 1 or 2, change the agent instruction, modify the temperature.
- **Expected result**: *Web*: at the last step the agent must answer without a tool. An orange alert appears if the context window is
  almost full or if the answer is truncated.

---

## Block D. External tools: MCP, sub-agent, dtctl, skills

### D1. Connect a Dynatrace MCP server
- **Objective**: add tools to an agent through configuration.
- **Actions**: create a platform token with `mcp-gateway:servers:invoke` and `read`, create `mcp.json` from the example in
  `/workspace/mcp`, open the Tools tab.
- **Expected result**: *Web*: the status of each MCP server and the discovered tools; a 401 or 403 error is explained in the tab.

### D2. Query Dynatrace through the sub-agent
- **Objective**: see one agent calling another.
- **Actions**: task "Which problems are open?".
- **Expected result**: *Web*: an `ask_dynatrace` card contains the sub-agent's activity (its steps and its MCP calls). *Dynatrace*:
  `agent.run` > `ask_dynatrace` > `dynatrace_agent` > MCP tool spans.

### D3. Limit the MCP tools
- **Objective**: reduce the context and improve tool selection.
- **Actions**: add `"tools": [...]` in `mcp.json`, compare before and after.
- **Expected result**: *Web*: fewer tools, fewer context alerts, better choices.

### D4. Configure dtctl
- **Objective**: give the agent a command line.
- **Actions**: in the terminal, `dtctl config set-context … --safety-level readonly`, `set-credentials …`, `dtctl doctor`, then a
  question about its environment.
- **Expected result**: *Web*: green dtctl badge and tool listed. *Dynatrace*: a `dtctl` tool span under the sub-agent. Commands
  that modify anything are refused. *(to be verified: selection of dtctl's current context)*

### D5. Give skills to the agent
- **Objective**: provide knowledge without bloating the context.
- **Actions**: clone `dynatrace-for-ai`, copy 2 or 3 skills into `/workspace/skills`, ask a question that requires DQL, remove
  the skills and compare.
- **Expected result**: *Web*: "Skills: N" line. *Dynatrace*: a `read_skill` span followed by different steps; queries are
  generally better with the skill.

### D6. Compare MCP, dtctl and skills
- **Objective**: choose the right access mode.
- **Actions**: ask the same question with each one alone (remove `mcp.json`, `dtctl-config` or the skills), then with all three.
- **Expected result**: *Dynatrace*: compare duration, number of steps and accuracy of the answers across the configurations.

### D7. Sub-agent or direct agent *(advanced, SSH access)*
- **Objective**: measure the value of the sub-agent.
- **Actions**: set `MCP_SUBAGENT=false` in `.env`, recreate `agent-api`, redo D2.
- **Expected result**: *Dynatrace*: the MCP tools appear directly under the main agent, with more context consumed and
  often a worse answer.

---

## Block E. Evaluate answers with dt-evals

### E1. Prepare the evaluation
- **Objective**: gather what is needed to judge.
- **Actions**: over SSH, `sudo scripts/set-rag-context.sh on`; create a platform token (read spans, write events and
  metrics); `scripts/generate-eval-traffic.sh 2 http://web`.
- **Expected result**: *Dynatrace*: traces with the RAG passages visible in the prompt. *Terminal*: `dt-evals doctor` all green.

### E2. Run an evaluation
- **Objective**: get scores on your own traces.
- **Actions**: `dt-evals configure` (service `ai-lab-rag-api-NN`), `run --dry-run`, then `run --since 1h --sample 20`.
- **Expected result**: *Dynatrace*: results in AI Observability > Evaluations and in DQL (`gen_ai.evaluation.result`), with score,
  explanation and link to the trace. *(to be verified: that dt-evals reads the attributes of our spans)*

### E3. Analyze the scores
- **Objective**: interpret a judge.
- **Actions**: identify the poorly scored answers; compare questions outside the documents and within the documents, with and without RAG.
- **Expected result**: *Dynatrace*: questions outside the documents are more often scored as hallucination; the judge's explanations are to be
  read critically.

### E4. Create a custom evaluator
- **Objective**: measure a project-specific criterion.
- **Actions**: `dt-evals evaluators add` for "does it cite its sources in square brackets?" and "does it answer in the language of the question?",
  `test`, then add it to the configuration.
- **Expected result**: *Dynatrace*: new scores in the Evaluations tab for these two criteria.

### E5. Compare two configurations and control quality
- **Objective**: detect quality drift.
- **Actions**: change the temperature or the system message, regenerate traffic, rerun, compare; try `--ci` with thresholds.
- **Expected result**: *Dynatrace*: different average scores and drift between the two series. *Terminal*: failure when a score falls below its threshold.

### E6. Evaluate the agent *(untested)*
- **Objective**: judge an agent, not just a chat.
- **Actions**: redo E2 with `ai-lab-agent-api-NN`.
- **Expected result**: *Dynatrace*: scores on the agent's final answers, depending on how dt-evals reads the agent's spans.

---

## Block F. Develop in VS Code web (`http://<vm>:8080/`)

### F1. Modify the knowledge base
- **Objective**: see the effect of a document on the answers.
- **Actions**: edit a file in `/workspace/docs`, click "Reindex the samples" in the web app, ask the question again.
- **Expected result**: *Web*: the new content appears in the cited passages.

### F2. Use the Continue chat with the local model
- **Objective**: see an untraced use of the same model.
- **Actions**: ask Continue to explain `telemetry.py`.
- **Expected result**: Continue answers with `qwen2.5:7b`. *Dynatrace*: this call does not appear, which allows discussing unobserved usage.

### F3. Add a tool to the agent *(advanced, SSH access)*
- **Objective**: understand how a tool becomes a span.
- **Actions**: add a function decorated with `@tool` in `agent.py` and its schema, rebuild (`docker compose up -d --build agent-api`),
  trigger it with a task.
- **Expected result**: *Web*: the new tool in the Tools tab and its calls. *Dynatrace*: a new tool span.

---

## Items the trainer must prepare
- A tenant with AI Observability, ingest tokens (OpenLLMetry) and, for blocks D and E, the ability for participants
  to create platform tokens (MCP scopes, data read, write of events and metrics for dt-evals).
- The shared judge LLM key (deployment script menu), with a spending cap.
- For block D: the participants' `mcp-gateway:*` permissions.

## What has not been verified end to end
Blocks D and E were tested with simulations (fake model, fake MCP server, fake dtctl), not with a real tenant: to be repeated once
before the training. Exercises B6 and E6 rely only on the expected behavior.
