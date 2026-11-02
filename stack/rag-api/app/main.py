"""RAG API : chat (SSE streaming), search, document management."""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# The telemetry (OpenLLMetry or OpenInference) must be initialised BEFORE ollama / chromadb are imported (see rag.py)
from app.telemetry import active_type, init_telemetry, service_name, switchable, task, source_file, workflow  # noqa: E402

init_telemetry()

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app import models_api, rag, telemetry_api  # noqa: E402

log = logging.getLogger("api")
DOCS_DIR = os.getenv("DOCS_DIR", "/data/docs")
MAX_UPLOAD = 5_000_000

state = {"models_ready": False, "bootstrap": "waiting_models", "error": ""}


async def bootstrap():
    """Wait for the models to be pulled, then index the sample documents once."""
    while True:
        try:
            if await rag.models_ready():
                break
        except Exception as exc:  # ollama not up yet
            state["error"] = str(exc)
        await asyncio.sleep(5)
    state["models_ready"] = True
    state["bootstrap"] = "ingesting"
    try:
        if await rag.count_chunks() == 0:
            await rag.ingest_dir(DOCS_DIR)
        state["bootstrap"] = "done"
        state["error"] = ""
    except Exception as exc:
        log.exception("bootstrap failed")
        state["bootstrap"] = "error"
        state["error"] = str(exc)


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(bootstrap())
    yield
    task.cancel()


app = FastAPI(title="AI lab RAG API", lifespan=lifespan)
app.include_router(telemetry_api.router)
app.include_router(models_api.router)


D = rag.DEFAULT_PARAMS


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = []
    model: str = Field("", max_length=100)                      # empty = default model (LLM_MODEL)
    use_rag: bool = True
    passages: int = Field(D["passages"], ge=1, le=8)            # RAG : number of passages retrieved
    system_prompt: str = Field("", max_length=4000)             # empty = default system message
    temperature: float = Field(D["temperature"], ge=0, le=2)    # sampling
    top_k: int = Field(D["top_k"], ge=1, le=100)                # sampling (token candidates)
    top_p: float = Field(D["top_p"], ge=0, le=1)                # sampling (nucleus)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    passages: int = Field(D["passages"], ge=1, le=8)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health")
async def health():
    chunks = 0
    if state["bootstrap"] == "done":
        try:
            chunks = await rag.count_chunks()
        except Exception:
            pass
    return {
        "ready": state["models_ready"] and state["bootstrap"] == "done",
        "models_ready": state["models_ready"],
        "bootstrap": state["bootstrap"],
        "error": state["error"],
        "chunks": chunks,
        "model": rag.LLM_MODEL,
        "embed_model": rag.EMBED_MODEL,
        "openllmetry": active_type() == "openllmetry",
        "openinference": active_type() == "openinference",
        "telemetry_switch": switchable(),
        "service": service_name(),
        "host": os.getenv("VM_FQDN", "localhost"),
    }


@app.get("/api/settings")
async def settings():
    """Default chat settings, used by the web UI to fill and reset the settings panel."""
    return {**D, "system_prompt": rag.SYSTEM_PROMPT, "system_prompts": rag.SYSTEM_PROMPTS}


@task("rag.retrieve")
async def retrieve(question: str, passages: int) -> list[dict]:
    return await rag.search(question, passages)


def chat_turn(req: ChatRequest, queue: asyncio.Queue):
    """Build the traced chat turn for one request.

    Same shape as the Traceloop examples: plain (non-generator) functions under @workflow / @task, so
    every span starts and ends cleanly and nests under rag.chat. The decorated functions only take
    small arguments (the question) because Traceloop records a decorated function's arguments and
    result as span input/output; the history and the retrieved passages are already in the LLM span.
    The SSE events reach the HTTP response through `queue`.
    """
    result = {"tokens": 0, "tps": 0.0}

    @workflow("rag.chat")
    async def rag_chat(question: str) -> str:
        sources: list[dict] = []
        if req.use_rag:
            sources = await retrieve(question, req.passages)
            await queue.put(sse("sources", sources))
        messages = rag.build_messages(question, req.history, sources, req.system_prompt)

        @task("rag.generate")
        async def generate() -> str:
            answer = []
            sampling = {"temperature": req.temperature, "top_k": req.top_k, "top_p": req.top_p}
            async for part in await rag.chat_stream(messages, model=req.model, **sampling):
                text = rag.field(rag.field(part, "message", {}), "content", "")
                if text:
                    answer.append(text)
                    await queue.put(sse("token", {"text": text}))
                if rag.field(part, "done", False):
                    result["tokens"] = rag.field(part, "eval_count", 0)
                    duration = rag.field(part, "eval_duration", 0) / 1e9
                    result["tps"] = round(result["tokens"] / duration, 2) if duration else 0.0
            return "".join(answer)

        return await generate()

    return rag_chat, result


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not state["models_ready"]:
        raise HTTPException(503, "Le modèle est encore en cours de téléchargement.")

    try:
        req.model = await rag.resolve_model(req.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    queue: asyncio.Queue = asyncio.Queue()
    rag_chat, result = chat_turn(req, queue)

    async def run():
        started = time.time()
        try:
            await rag_chat(req.message)
            await queue.put(sse("done", {**result, "total_s": round(time.time() - started, 1)}))
        except Exception as exc:
            log.exception("chat failed")
            await queue.put(sse("error", {"text": f"Erreur pendant la génération : {exc}"}))
        finally:
            await queue.put(None)

    async def stream():
        # the turn runs in its own task (its own trace context); this generator only relays events
        worker = asyncio.create_task(run())
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


@app.get("/api/observability/code")
async def observability_code():
    """Source of the telemetry setup (OpenLLMetry or OpenInference), shown in the web UI (Observability tab)."""
    name = source_file()
    return {"file": f"app/{name}", "code": Path(__file__).with_name(name).read_text(encoding="utf-8")}


@app.post("/api/search")
async def search(req: SearchRequest):
    if not state["models_ready"]:
        raise HTTPException(503, "Le modèle d'embedding n'est pas encore prêt.")
    return {"sources": await rag.search(req.query, req.passages)}


@app.get("/api/documents")
async def documents():
    if state["bootstrap"] != "done":
        return []
    return await rag.list_documents()


@app.delete("/api/documents/{source}")
async def delete_document(source: str):
    await rag.delete_document(Path(source).name)
    return {"deleted": source}


@app.post("/api/ingest")
async def ingest():
    if not state["models_ready"]:
        raise HTTPException(503, "Le modèle d'embedding n'est pas encore prêt.")
    return {"indexed": await rag.ingest_dir(DOCS_DIR)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not state["models_ready"]:
        raise HTTPException(503, "Le modèle d'embedding n'est pas encore prêt.")
    name = Path(file.filename or "document.txt").name
    if Path(name).suffix.lower() not in rag.ALLOWED_EXT:
        raise HTTPException(415, "Formats acceptés : .txt, .md, .pdf")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Fichier trop volumineux (5 Mo maximum).")
    text = rag.extract_text(name, data)
    if not text.strip():
        raise HTTPException(422, "Aucun texte exploitable dans ce fichier.")
    return {"source": name, "chunks": await rag.ingest_text(name, text)}
