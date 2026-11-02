"""RAG services : chunking, embeddings (Ollama), vector store (ChromaDB), prompt building."""
import asyncio
import io
import logging
import os
import time
from pathlib import Path

import chromadb
import ollama
from chromadb.config import Settings

from app.telemetry import HISTORY_PREFIX, RAG_PREFIX

log = logging.getLogger("rag")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
COLLECTION = os.getenv("COLLECTION", "training_docs")
ALLOWED_EXT = {".md", ".txt", ".pdf"}

# Default system message in each language of the web UI (the UI picks the one of the selected language).
SYSTEM_PROMPTS = {
    "fr": (
        "Tu es l'assistant d'un atelier de formation sur l'IA générative et l'observabilité. "
        "Réponds dans la langue de la question, de façon claire et concise. "
        "Quand des passages de documents sont fournis, appuie-toi dessus et cite leur numéro "
        "entre crochets, par exemple [1]. "
        "Si les passages ne contiennent pas la réponse, dis-le, puis réponds avec tes "
        "connaissances générales en précisant que cela ne vient pas des documents."
    ),
    "en": (
        "You are the assistant of a training workshop on generative AI and observability. "
        "Answer in the language of the question, clearly and concisely. "
        "When document passages are provided, rely on them and cite their number "
        "in square brackets, for example [1]. "
        "If the passages do not contain the answer, say so, then answer from your "
        "general knowledge, making clear that it does not come from the documents."
    ),
    "es": (
        "Eres el asistente de un taller de formación sobre IA generativa y observabilidad. "
        "Responde en el idioma de la pregunta, de forma clara y concisa. "
        "Cuando se proporcionen fragmentos de documentos, apóyate en ellos y cita su número "
        "entre corchetes, por ejemplo [1]. "
        "Si los fragmentos no contienen la respuesta, dilo y luego responde con tus "
        "conocimientos generales, aclarando que no proceden de los documentos."
    ),
    "de": (
        "Du bist der Assistent eines Schulungsworkshops zu generativer KI und Observability. "
        "Antworte in der Sprache der Frage, klar und knapp. "
        "Wenn Dokumentpassagen bereitgestellt werden, stütze dich darauf und nenne ihre Nummer "
        "in eckigen Klammern, zum Beispiel [1]. "
        "Wenn die Passagen die Antwort nicht enthalten, sage das und antworte dann mit deinem "
        "Allgemeinwissen, mit dem Hinweis, dass dies nicht aus den Dokumenten stammt."
    ),
    "it": (
        "Sei l'assistente di un laboratorio di formazione sull'IA generativa e sull'observability. "
        "Rispondi nella lingua della domanda, in modo chiaro e conciso. "
        "Quando vengono forniti passaggi di documenti, basati su di essi e cita il loro numero "
        "tra parentesi quadre, ad esempio [1]. "
        "Se i passaggi non contengono la risposta, dillo, poi rispondi con le tue "
        "conoscenze generali precisando che non provengono dai documenti."
    ),
}
SYSTEM_PROMPT = SYSTEM_PROMPTS["fr"]

# default chat settings (editable from the web UI, sent with every chat request)
DEFAULT_PARAMS = {"temperature": 0.3, "top_k": 40, "top_p": 0.9, "passages": 3}

_client = ollama.AsyncClient(host=OLLAMA_HOST)
_collection = None


def field(obj, key, default=None):
    """Read a field from an ollama response (pydantic object or dict)."""
    try:
        value = obj[key]
    except Exception:
        value = getattr(obj, key, default)
    return default if value is None else value


# --------------------------------------------------------------------------- chroma

def _get_collection_sync():
    global _collection
    if _collection is not None:
        return _collection
    last = None
    for _ in range(30):
        try:
            client = chromadb.HttpClient(
                host=CHROMA_HOST, port=CHROMA_PORT, settings=Settings(anonymized_telemetry=False)
            )
            _collection = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
            return _collection
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError(f"ChromaDB unreachable: {last}")


async def count_chunks() -> int:
    return await asyncio.to_thread(lambda: _get_collection_sync().count())


async def list_documents() -> list[dict]:
    def _list():
        data = _get_collection_sync().get(include=["metadatas"])
        counts: dict[str, int] = {}
        for meta in data["metadatas"] or []:
            counts[meta["source"]] = counts.get(meta["source"], 0) + 1
        return [{"source": s, "chunks": c} for s, c in sorted(counts.items())]
    return await asyncio.to_thread(_list)


async def delete_document(source: str) -> None:
    await asyncio.to_thread(lambda: _get_collection_sync().delete(where={"source": source}))


# --------------------------------------------------------------------------- models

async def models_ready() -> bool:
    response = await _client.list()
    names = {field(m, "model", "") for m in field(response, "models", [])}
    embed_names = {EMBED_MODEL, f"{EMBED_MODEL}:latest"}
    return LLM_MODEL in names and bool(names & embed_names)


def _base(name: str) -> str:
    return name[:-len(":latest")] if name.endswith(":latest") else name


async def list_models() -> list[dict]:
    """Installed chat models (embedding models left out) with what they can do: tools, vision."""
    response = await _client.list()
    names = [field(m, "model", "") for m in field(response, "models", [])]
    sizes = {field(m, "model", ""): field(m, "size", 0) for m in field(response, "models", [])}

    async def describe(name: str):
        try:
            caps = list(field(await _client.show(name), "capabilities", None) or [])
        except Exception:
            caps = []
        return name, caps

    models = []
    for name, caps in await asyncio.gather(*(describe(n) for n in names if n)):
        if "embedding" in caps or _base(name) == _base(EMBED_MODEL):
            continue
        models.append({"name": name, "size_gb": round(sizes.get(name, 0) / 1e9, 1),
                       "tools": "tools" in caps, "vision": "vision" in caps})
    return sorted(models, key=lambda m: m["name"])


async def resolve_model(requested: str = "") -> str:
    """Model of a request: the one asked for if it is installed, the default one when empty. ValueError otherwise."""
    requested = (requested or "").strip()
    if not requested or _base(requested) == _base(LLM_MODEL):
        return LLM_MODEL
    installed = {_base(field(m, "model", "")) for m in field(await _client.list(), "models", [])}
    if _base(requested) not in installed:
        raise ValueError(f"model {requested!r} is not installed")
    return requested


async def embed(texts: list[str]) -> list[list[float]]:
    response = await _client.embed(model=EMBED_MODEL, input=texts)
    return [list(e) for e in field(response, "embeddings", [])]


async def chat_stream(messages: list[dict], temperature: float, top_k: int, top_p: float, model: str = ""):
    return await _client.chat(
        model=model or LLM_MODEL,
        messages=messages,
        stream=True,
        options={"temperature": temperature, "top_k": top_k, "top_p": top_p, "num_ctx": 4096},
    )


# --------------------------------------------------------------------------- ingestion

def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = text.replace("\r", "").strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            if cut == -1:
                cut = text.rfind(". ", start + size // 2, end)
            if cut != -1:
                end = cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_text(filename: str, data: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return data.decode("utf-8", errors="replace")


async def ingest_text(source: str, text: str) -> int:
    chunks = chunk_text(text)
    if not chunks:
        return 0
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), 16):
        batch = ["search_document: " + c for c in chunks[i:i + 16]]
        embeddings += await embed(batch)

    def _write():
        col = _get_collection_sync()
        col.delete(where={"source": source})
        col.add(
            ids=[f"{source}:{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": source, "chunk": i} for i in range(len(chunks))],
        )

    await asyncio.to_thread(_write)
    log.info("indexed %s (%d passages)", source, len(chunks))
    return len(chunks)


DOCS_LANG = os.getenv("DOCS_LANG", "en").strip().lower()


def _wanted(file: Path, names: set[str]) -> bool:
    """The knowledge base uses the English documents only (DOCS_LANG=en, the default).

    Convention: `name.md` is the English version and `name.fr.md` the French one. French files are indexed only when
    DOCS_LANG=fr, and then they replace their English counterpart. Other files (.txt, .pdf, .md without a French
    version) are always indexed.
    """
    if file.name.endswith(".fr.md"):
        return DOCS_LANG == "fr"
    if file.suffix.lower() == ".md" and file.name[:-3] + ".fr.md" in names:
        return DOCS_LANG != "fr"
    return True


async def ingest_dir(path: str) -> dict[str, int]:
    result = {}
    files = sorted(Path(path).glob("*"))
    names = {f.name for f in files}
    for file in files:
        if file.suffix.lower() in ALLOWED_EXT and file.is_file() and _wanted(file, names):
            text = extract_text(file.name, file.read_bytes())
            result[file.name] = await ingest_text(file.name, text)
    return result


# --------------------------------------------------------------------------- retrieval

async def search(query: str, k: int = 3) -> list[dict]:
    [vector] = await embed(["search_query: " + query])

    def _query():
        col = _get_collection_sync()
        if col.count() == 0:
            return None
        return col.query(
            query_embeddings=[vector],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

    result = await asyncio.to_thread(_query)
    if not result:
        return []
    out = []
    rows = zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
    for n, (doc, meta, dist) in enumerate(rows, 1):
        out.append({
            "n": n,
            "source": meta["source"],
            "chunk": meta["chunk"],
            "text": doc,
            "score": round(min(1.0, max(0.0, 1 - dist)), 3),
        })
    return out


def build_messages(question: str, history: list[dict], sources: list[dict],
                   system_prompt: str = "") -> list[dict]:
    """Messages sent to the model, ordered for readable traces.

    1. the user question, alone (the first input shown by Dynatrace AI Observability),
    2. the system instruction,
    3. a user message with the RAG passages (if any), starting with RAG_PREFIX,
    4. a user message with the previous turns (if any), starting with HISTORY_PREFIX.
    Messages 3 and 4 are sent to the model but removed from the exported trace (telemetry._strip_history).
    Ollama gathers every system message into the system prompt whatever its position.
    """
    messages = [
        {"role": "user", "content": question},
        {"role": "system", "content": system_prompt.strip() or SYSTEM_PROMPT},
    ]
    if sources:
        context = "\n\n".join(f"[{s['n']}] (source : {s['source']})\n{s['text']}" for s in sources)
        messages.append({"role": "user", "content": (
            f"{RAG_PREFIX}\n\n{context}\n\n"
            "Réponds à la question de l'utilisateur ci-dessus en t'appuyant sur ces passages.")})
    previous = []
    for item in history[-6:]:
        role, content = item.get("role"), str(item.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            previous.append(f"{'Utilisateur' if role == 'user' else 'Assistant'} : {content}")
    if previous:
        messages.append({"role": "user", "content": (
            f"{HISTORY_PREFIX}\n\n" + "\n\n".join(previous) + "\n\n"
            "Tiens compte de ces échanges pour répondre à la question de l'utilisateur ci-dessus.")})
    return messages
