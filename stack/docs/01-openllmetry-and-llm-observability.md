# OpenLLMetry and observability of LLM applications

[Version française](01-openllmetry-and-llm-observability.fr.md)

OpenLLMetry is an open source project (Traceloop) that adds generative AI application instrumentation to OpenTelemetry. It is installed with the Traceloop SDK and produces traces, metrics and logs in the OpenTelemetry format (OTLP).

## What the SDK can do

By default, the SDK detects the AI libraries present in the application (model clients, vector databases, orchestration frameworks) and turns each call into a span, with the model name, the number of tokens, the duration and, if allowed, the text of the prompts and responses.

## What this workshop traces

The workshop uses the configuration documented by Dynatrace (Traceloop.init towards the tenant's OTLP endpoint, delta temporality), with the SDK's Ollama instrumentation and OpenLLMetry decorators to describe the application's activity. The workshop's own additions are limited to masking data before it is sent.

- **the chat** (service `ai-lab-rag-api-NN`, NN being the VM number): a `rag.chat` workflow and its two steps, `rag.retrieve` (embedding of the question then search in ChromaDB) and `rag.generate` (call to the qwen2.5:7b model). The duration of each span shows where the time goes;
- **the agent** (service `ai-lab-agent-api-NN`): an `agent.run` span, a series of `agent.step` spans (one model call each), one span per tool called (`calculator`, `search_documents`, `dtctl`, `read_skill`...) and, with an MCP server or dtctl, `ask_dynatrace` then `dynatrace_agent` for the Dynatrace sub-agent;
- **the model call**: produced by OpenLLMetry's Ollama instrumentation. The span carries the model name, the request settings (temperature, top K, top P), the number of input tokens, output tokens and the total, and the streaming mode.

## What the exported prompt contains

The model call span shows the **user's question**, the **system message** and the model's **response**. The **conversation history** and the **RAG document passages** are sent to the model but removed from the span before export, by an SDK post-processing callback (span_postprocess_callback). The input token count still includes them: it is therefore larger than the prompt visible in the trace.

To keep the RAG passages in the traces (for example to judge the faithfulness of answers with dt-evals), an administrator runs `sudo scripts/set-rag-context.sh on` on the VM. The history is never exported.

## In this workshop

The application is written in Python (FastAPI). When the OpenLLMetry option is enabled at deployment (or with `scripts/set-openllmetry.sh` for the chat and `scripts/set-agent-openllmetry.sh` for the agent), the Traceloop SDK is initialized at startup and sends traces and metrics to the Dynatrace tenant's OTLP endpoint. When the option is disabled, the application works the same way but emits no telemetry.

Changing the temperature, top K, top P or the system message in the interface changes the settings visible in the trace of the next question. In Dynatrace, the traces appear in distributed traces and in AI Observability, and the dt-evals tool lets an LLM judge score the responses.
