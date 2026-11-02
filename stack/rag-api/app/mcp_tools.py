"""MCP tools for the agent : remote MCP servers declared by the participants in a mcp.json file.

The participants create the file themselves (in the VS Code web, folder /workspace/mcp, see stack/mcp/README.md):

    {
      "servers": {
        "dynatrace-mcp": {
          "url": "https://<env>.apps.dynatrace.com/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp",
          "headers": { "Authorization": "Bearer ${DT_PLATFORM_TOKEN}" },
          "tools": ["list_problems", "execute_dql"]          <- optional allow-list
        }
      }
    }

The file is read again whenever it changes, no restart needed. Only remote (HTTP) servers are supported.
Every tool call opens its own short MCP session (simple and robust); tool errors are returned to the model.
"""
import asyncio
import json
import logging
import os
import re
import time

log = logging.getLogger("mcp")

MCP_FILE = os.getenv("MCP_CONFIG", "/workspace/mcp/mcp.json")
from app.limits import clip, compact
CACHE_SECONDS = 60

_cache = {"key": None, "at": 0.0, "tools": [], "status": {"configured": False, "servers": [], "error": ""}}
_routes: dict[str, tuple[str, str, dict]] = {}   # tool name -> (url, original tool name, headers)


def _expand(value):
    """Replace ${VAR} by the environment variable VAR in every string of the configuration."""
    if isinstance(value, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def read_config() -> dict[str, dict]:
    """Servers declared in the file ({} if the file is missing); raises ValueError if it is invalid."""
    try:
        with open(MCP_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"mcp.json invalide : {exc}")
    servers = raw.get("servers") or raw.get("mcpServers") or {}
    if not isinstance(servers, dict):
        raise ValueError("mcp.json : « servers » doit être un objet")
    return _expand(servers)


async def _list_server_tools(url: str, headers: dict):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(url, headers=headers, timeout=10) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return (await session.list_tools()).tools


_lock = asyncio.Lock()
_background = set()


def _file_key():
    try:
        return os.stat(MCP_FILE).st_mtime
    except OSError:
        return None


def _stale() -> bool:
    return _file_key() != _cache["key"] or time.time() - _cache["at"] >= CACHE_SECONDS


def refresh_soon() -> None:
    """Non-blocking refresh (status endpoints): discovery runs in the background, the cache is served meanwhile."""
    if _stale() and not _lock.locked():
        task = asyncio.create_task(refresh())
        _background.add(task)
        task.add_done_callback(_background.discard)


async def refresh(force: bool = False) -> None:
    """(Re)discover the tools of the declared servers when the file changed or the cache is old."""
    async with _lock:
        if force or _stale():
            await _discover()


async def _discover() -> None:
    key = _file_key()

    tools, servers, error = [], [], ""
    _routes.clear()
    try:
        config = read_config()
    except ValueError as exc:
        config, error = {}, str(exc)

    for name, server in config.items():
        entry = {"name": name, "url": server.get("url", ""), "ok": False, "error": "", "tools": []}
        servers.append(entry)
        if not entry["url"]:
            entry["error"] = "url manquante (seuls les serveurs MCP distants sont gérés)"
            continue
        headers = {str(k): str(v) for k, v in (server.get("headers") or {}).items()}
        try:
            found = await _list_server_tools(entry["url"], headers)
        except BaseException as exc:      # includes anyio ExceptionGroup raised by the transport
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            entry["error"] = _short_error(exc)
            log.warning("MCP server %s unreachable: %s", name, entry["error"])
            continue
        allowed = set(server.get("tools") or [])
        for t in found:
            if allowed and t.name not in allowed:
                continue
            public = t.name if t.name not in _routes else f"{name}__{t.name}"
            _routes[public] = (entry["url"], t.name, headers)
            entry["tools"].append(public)
            tools.append({"type": "function", "function": {
                "name": public,
                "description": (t.description or "")[:1000],
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            }, "_source": name})
        entry["ok"] = True

    _cache.update(key=key, at=time.time(), tools=tools,
                  status={"configured": bool(config) or bool(error), "servers": servers, "error": error})


def _short_error(exc: BaseException) -> str:
    while getattr(exc, "exceptions", None):          # unwrap ExceptionGroup
        exc = exc.exceptions[0]
    text = str(exc) or exc.__class__.__name__
    if "403" in text:
        text += " (token ou droits insuffisants : mcp-gateway:servers:invoke / read ?)"
    elif "401" in text:
        text += " (token invalide ou expiré)"
    return text[:300]


def tool_schemas() -> list[dict]:
    """Ollama tool definitions of the MCP tools (without the internal _source marker)."""
    return [{k: v for k, v in t.items() if k != "_source"} for t in _cache["tools"]]


def status() -> dict:
    return {**_cache["status"], "file": MCP_FILE, "tools": [t["function"]["name"] for t in _cache["tools"]]}


def has_tool(name: str) -> bool:
    return name in _routes


def describe() -> list[dict]:
    return [{"name": t["function"]["name"], "description": t["function"]["description"], "source": t["_source"]}
            for t in _cache["tools"]]


async def call(name: str, arguments: dict) -> str:
    """Call one MCP tool; errors come back as text for the model."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    url, original, headers = _routes[name]
    try:
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(original, arguments or {})
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return f"Erreur MCP : {_short_error(exc)}"
    parts = []
    for item in result.content or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else f"[{getattr(item, 'type', 'contenu')}]")
    out = compact("\n".join(parts)) or "(résultat vide)"
    if getattr(result, "isError", False):
        out = "Erreur de l'outil : " + out
    return clip(out)
