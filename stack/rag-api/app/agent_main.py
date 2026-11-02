"""Agent API : agentic AI on the same local model as the chat (SSE streaming of the agent steps).

Runs from the same image as the RAG API, with its own OpenLLMetry service name (ai-lab-agent-api-<vm number>).
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# The telemetry (OpenLLMetry or OpenInference) must be initialised BEFORE ollama / chromadb are imported (see rag.py)
from app.telemetry import active_type, init_telemetry, service_name, switchable, source_file  # noqa: E402

init_telemetry()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app import dtctl_tool, mcp_tools, models_api, rag, skills, telemetry_api  # noqa: E402
from app.agent import (AGENT_SYSTEM_PROMPT, AGENT_SYSTEM_PROMPTS, ASK_DYNATRACE, DEFAULT_AGENT_PARAMS, NUM_CTX,
                       TOOLS, agent_turn, dynatrace_tool_schemas, subagent_active)  # noqa: E402

log = logging.getLogger("agent-api")
D = DEFAULT_AGENT_PARAMS
app = FastAPI(title="AI lab agent API")
app.include_router(telemetry_api.router)
app.include_router(models_api.router)


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = []
    model: str = Field("", max_length=100)                      # empty = default model (LLM_MODEL)
    system_prompt: str = Field("", max_length=4000)             # empty = default agent instruction
    max_steps: int = Field(D["max_steps"], ge=1, le=8)          # model calls allowed for one task
    temperature: float = Field(D["temperature"], ge=0, le=2)
    top_k: int = Field(D["top_k"], ge=1, le=100)
    top_p: float = Field(D["top_p"], ge=0, le=1)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health")
async def health():
    ready, chunks = False, 0
    mcp_tools.refresh_soon()
    mcp = mcp_tools.status()
    try:
        ready = await rag.models_ready()
        chunks = await rag.count_chunks() if ready else 0
    except Exception:
        pass
    return {
        "ready": ready,
        "models_ready": ready,
        "model": rag.LLM_MODEL,
        "chunks": chunks,
        "openllmetry": active_type() == "openllmetry",
        "openinference": active_type() == "openinference",
        "telemetry_switch": switchable(),
        "service": service_name(),
        "tools": [t["function"]["name"] for t in TOOLS] + (["ask_dynatrace"] if subagent_active() else [])
                 + [t["function"]["name"] for t in dynatrace_tool_schemas()],
        "dtctl": dtctl_tool.status(),
        "skills": skills.status(),
        "subagent": subagent_active(),
        "mcp": mcp,
        "num_ctx": NUM_CTX,
        "host": os.getenv("VM_FQDN", "localhost"),
    }


@app.get("/api/settings")
async def settings():
    return {**D, "system_prompt": AGENT_SYSTEM_PROMPT, "system_prompts": AGENT_SYSTEM_PROMPTS}


@app.get("/api/tools")
async def tools():
    mcp_tools.refresh_soon()
    local = [{"name": t["function"]["name"], "description": t["function"]["description"], "source": "local"} for t in TOOLS]
    sub = ([{"name": "ask_dynatrace", "description": ASK_DYNATRACE["function"]["description"], "source": "subagent"}]
           if subagent_active() else [])
    others = [{"name": t["function"]["name"], "description": t["function"]["description"], "source": src, "badge": src}
              for src, group in (("dtctl", [dtctl_tool.SCHEMA] if dtctl_tool.available() else []),
                                 ("skills", skills.schemas() if dynatrace_tool_schemas() else []))
              for t in group]
    return local + sub + mcp_tools.describe() + others


@app.get("/api/observability/code")
async def observability_code():
    """Source of the telemetry setup (OpenLLMetry or OpenInference), shown in the web UI (Observability tab)."""
    name = source_file()
    return {"file": f"app/{name}", "code": Path(__file__).with_name(name).read_text(encoding="utf-8")}


@app.post("/api/chat")
async def chat(req: AgentRequest):
    try:
        ready = await rag.models_ready()
    except Exception:
        ready = False
    if not ready:
        raise HTTPException(503, "Le modèle est encore en cours de téléchargement.")

    try:
        req.model = await rag.resolve_model(req.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    queue: asyncio.Queue = asyncio.Queue()
    run, totals = agent_turn(req, queue, sse)

    async def work():
        started = time.time()
        try:
            await run(req.message)
            await queue.put(sse("done", {**totals, "total_s": round(time.time() - started, 1)}))
        except Exception as exc:
            log.exception("agent failed")
            await queue.put(sse("error", {"text": f"Erreur pendant l'exécution de l'agent : {exc}"}))
        finally:
            await queue.put(None)

    async def stream():
        # the run lives in its own task (its own trace context); this generator only relays events
        worker = asyncio.create_task(work())
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            worker.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
