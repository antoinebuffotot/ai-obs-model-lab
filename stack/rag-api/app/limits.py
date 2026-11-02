"""Size limits of the tool results given back to the model (shared by the local tools, MCP, dtctl and the sub-agent).

A result larger than the limit is cut, and the model is TOLD it was cut: a silent cut makes the model believe it has
the whole answer (e.g. it reports 1 problem out of 4 because the other three were beyond the limit).
"""
import json
import os

TOOL_RESULT_CHARS = int(os.getenv("TOOL_RESULT_CHARS", "6000"))


def compact(text: str) -> str:
    """Re-serialise a JSON text without indentation: same data, far fewer characters (so fewer cut results)."""
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            return json.dumps(json.loads(stripped), ensure_ascii=False, separators=(",", ":"))
        except ValueError:
            pass
    return text


def clip(text: str, limit: int = 0) -> str:
    """Cut `text` to `limit` characters and say so at the end, so the model knows the result is incomplete."""
    limit = limit or TOOL_RESULT_CHARS
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return (text[:limit] + f"\n[... result truncated: {omitted} characters omitted, the list above may be incomplete; "
            "narrow the query (filters, shorter time range, fewer fields) and ask again]")
