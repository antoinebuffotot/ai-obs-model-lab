"""GET /api/models, POST /api/models/pull : list the local models and download a new one (shared by the chat and the agent API)."""
import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import rag

router = APIRouter()
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")   # name[:tag], hf.co/org/repo[:quant]


class PullRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/api/models")
async def models():
    try:
        return {"default": rag.LLM_MODEL, "models": await rag.list_models()}
    except Exception as exc:
        raise HTTPException(503, f"Ollama indisponible : {exc}")


@router.post("/api/models/pull")
async def pull(req: PullRequest):
    """Download a model, progress as SSE events (progress {status, total, completed} then done, or error)."""
    name = req.name.strip()
    if not NAME.match(name):
        raise HTTPException(400, "invalid model name")

    async def stream():
        try:
            async for part in await rag._client.pull(name, stream=True):
                yield sse("progress", {"status": rag.field(part, "status", ""), "total": rag.field(part, "total", 0) or 0,
                                       "completed": rag.field(part, "completed", 0) or 0})
            yield sse("done", {"name": name})
        except Exception as exc:
            yield sse("error", {"text": str(exc)})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
