"""Agentic AI : a tool-calling loop on the same local model (Ollama) as the chat.

The agent receives a task, decides which tools to call (document search, calculator, clock, document
list), reads the results and repeats until it can answer, within a step limit.

Traces (OpenLLMetry, see telemetry.py):
    agent.run                @agent   the whole task (input = the task, output = the final answer)
    ├── agent.step           @task    one model call (the Ollama LLM span nests inside)
    ├── search_documents     @tool    one span per tool call
    └── ask_dynatrace        @tool    with MCP: delegates to the Dynatrace sub-agent
        └── dynatrace_agent  @agent   its own steps (LLM) and one @tool span per MCP call
Plain async functions only (no generators) so every span starts and ends cleanly; the events shown
in the web UI reach the HTTP response through a queue.
"""
import ast
import asyncio
import json
import logging
import operator
import os
import time
from datetime import datetime, timezone

from app import dtctl_tool, mcp_tools, rag, skills
from app.rag import field
from app.limits import clip
from app.telemetry import HISTORY_PREFIX, agent, task, tool

log = logging.getLogger("agent")

# Default agent instruction in each language of the web UI (the UI picks the one of the selected language).
AGENT_SYSTEM_PROMPTS = {
    "fr": (
        "Tu es un agent IA autonome dans un atelier de formation sur l'IA générative et l'observabilité. "
        "Pour accomplir la tâche de l'utilisateur, tu disposes d'outils : utilise-les dès qu'ils apportent "
        "une information fiable (documents de l'atelier, calcul exact, date et heure) au lieu de deviner. "
        "D'autres outils (par exemple pour interroger une plateforme Dynatrace) peuvent s'ajouter à ceux-ci. "
        "Tu peux appeler plusieurs outils à la suite. Quand tu as assez d'éléments, réponds directement, "
        "de façon claire et concise, dans la langue de la tâche, et cite les documents utilisés "
        "(nom du fichier) quand tu t'appuies dessus."
    ),
    "en": (
        "You are an autonomous AI agent in a training workshop on generative AI and observability. "
        "To accomplish the user's task you have tools: use them whenever they provide reliable "
        "information (workshop documents, exact calculation, date and time) instead of guessing. "
        "Other tools (for example to query a Dynatrace platform) may be added to these. "
        "You can call several tools in a row. When you have enough information, answer directly, "
        "clearly and concisely, in the language of the task, and cite the documents you used "
        "(file name) when you rely on them."
    ),
    "es": (
        "Eres un agente de IA autónomo en un taller de formación sobre IA generativa y observabilidad. "
        "Para cumplir la tarea del usuario dispones de herramientas: úsalas siempre que aporten "
        "información fiable (documentos del taller, cálculo exacto, fecha y hora) en lugar de adivinar. "
        "Pueden añadirse otras herramientas (por ejemplo, para consultar una plataforma Dynatrace). "
        "Puedes llamar a varias herramientas seguidas. Cuando tengas suficiente información, responde "
        "directamente, de forma clara y concisa, en el idioma de la tarea, y cita los documentos "
        "utilizados (nombre del archivo) cuando te apoyes en ellos."
    ),
    "de": (
        "Du bist ein autonomer KI-Agent in einem Schulungsworkshop zu generativer KI und Observability. "
        "Zur Erledigung der Aufgabe des Benutzers stehen dir Werkzeuge zur Verfügung: Nutze sie, sobald "
        "sie verlässliche Informationen liefern (Workshop-Dokumente, exakte Berechnung, Datum und Uhrzeit), "
        "statt zu raten. Weitere Werkzeuge (zum Beispiel zur Abfrage einer Dynatrace-Plattform) können "
        "hinzukommen. Du kannst mehrere Werkzeuge nacheinander aufrufen. Wenn du genug Informationen hast, "
        "antworte direkt, klar und knapp, in der Sprache der Aufgabe, und nenne die verwendeten "
        "Dokumente (Dateiname), wenn du dich darauf stützt."
    ),
    "it": (
        "Sei un agente IA autonomo in un laboratorio di formazione sull'IA generativa e sull'observability. "
        "Per svolgere il compito dell'utente hai a disposizione degli strumenti: usali ogni volta che "
        "forniscono informazioni affidabili (documenti del laboratorio, calcolo esatto, data e ora) invece "
        "di tirare a indovinare. Possono aggiungersi altri strumenti (ad esempio per interrogare una "
        "piattaforma Dynatrace). Puoi chiamare più strumenti di seguito. Quando hai abbastanza elementi, "
        "rispondi direttamente, in modo chiaro e conciso, nella lingua del compito, e cita i documenti "
        "usati (nome del file) quando ti basi su di essi."
    ),
}
AGENT_SYSTEM_PROMPT = AGENT_SYSTEM_PROMPTS["fr"]

# Context window of the agent: the tool definitions, the tool results and the answers all share it.
# 4096 is too small as soon as MCP tools are added (their schemas are long): the model then loses the
# beginning of the prompt or stops in the middle of its answer.
NUM_CTX = int(os.getenv("AGENT_NUM_CTX", "8192"))

DEFAULT_AGENT_PARAMS = {"temperature": 0.2, "top_k": 40, "top_p": 0.9, "max_steps": 5}

TOOLS = [
    {"type": "function", "function": {
        "name": "search_documents",
        "description": "Cherche dans les documents de l'atelier (base de connaissances) les passages les plus "
                       "pertinents pour une requête. À utiliser pour toute question sur l'atelier, OpenLLMetry, "
                       "le RAG ou l'infrastructure.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "La requête de recherche, en langage naturel"},
            "passages": {"type": "integer", "description": "Nombre de passages à retourner (1 à 5, défaut 3)"}}}}},
    {"type": "function", "function": {
        "name": "list_documents",
        "description": "Liste les documents indexés dans la base de connaissances.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Calcule exactement une expression arithmétique (+ - * / // % ** et parenthèses).",
        "parameters": {"type": "object", "required": ["expression"], "properties": {
            "expression": {"type": "string", "description": "Par exemple : (12.5 + 7) * 3"}}}}},
    {"type": "function", "function": {
        "name": "get_current_time",
        "description": "Donne la date et l'heure actuelles (UTC).",
        "parameters": {"type": "object", "properties": {}}}},
]


# --------------------------------------------------------------------------- tools

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exposant trop grand")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("expression non autorisée")


@tool("search_documents")
async def tool_search_documents(query: str, passages: int = 3) -> str:
    sources = await rag.search(query, max(1, min(int(passages), 5)))
    if not sources:
        return "Aucun passage trouvé."
    return "\n\n".join(f"[{s['n']}] (source : {s['source']}, pertinence {round(s['score'] * 100)} %)\n{s['text']}"
                       for s in sources)


@tool("list_documents")
async def tool_list_documents() -> str:
    docs = await rag.list_documents()
    return "\n".join(f"- {d['source']} ({d['chunks']} passages)" for d in docs) or "Aucun document indexé."


@tool("calculator")
def tool_calculator(expression: str) -> str:
    try:
        return str(_eval(ast.parse(str(expression).strip(), mode="eval")))
    except ZeroDivisionError:
        return "Erreur : division par zéro."
    except Exception as exc:
        return f"Erreur : {exc}"


@tool("get_current_time")
def tool_get_current_time() -> str:
    return datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M:%S UTC")


@tool("dtctl")
async def tool_dtctl(command: str) -> str:
    return await dtctl_tool.run(command)


@tool("list_skills")
def tool_list_skills() -> str:
    return skills.list_skills()


@tool("read_skill")
def tool_read_skill(name: str, reference: str = "") -> str:
    return skills.read_skill(name, reference)


async def run_mcp_tool(name: str, args: dict) -> str:
    """One span per MCP tool call, named after the tool (the decorator is built at call time)."""
    @tool(name)
    async def call(arguments: dict) -> str:
        return await mcp_tools.call(name, arguments)

    return await call(args)


async def run_tool(name: str, args: dict) -> str:
    """Execute one tool call; errors are returned to the model as text, never raised."""
    try:
        if name == "search_documents":
            result = await tool_search_documents(str(args.get("query", "")), args.get("passages", 3))
        elif name == "list_documents":
            result = await tool_list_documents()
        elif name == "calculator":
            result = tool_calculator(str(args.get("expression", "")))
        elif name == "get_current_time":
            result = tool_get_current_time()
        elif name == "dtctl":
            result = await tool_dtctl(str(args.get("command", "")))
        elif name == "list_skills":
            result = tool_list_skills()
        elif name == "read_skill":
            result = tool_read_skill(str(args.get("name", "")), str(args.get("reference", "") or ""))
        elif mcp_tools.has_tool(name):
            result = await run_mcp_tool(name, args)
        else:
            return f"Erreur : outil inconnu « {name} »."
    except Exception as exc:
        log.exception("tool %s failed", name)
        return f"Erreur pendant l'exécution de l'outil : {exc}"
    return clip(str(result))


# --------------------------------------------------------------------------- messages

def build_agent_messages(task_text: str, history: list[dict], system_prompt: str = "") -> list[dict]:
    """Same layout as rag.build_messages: the task first (first input shown in Dynatrace), then the
    system instruction, then the previous turns in a marked message that the trace callback removes."""
    messages = [
        {"role": "user", "content": task_text},
        {"role": "system", "content": system_prompt.strip() or AGENT_SYSTEM_PROMPT},
    ]
    previous = []
    for item in history[-6:]:
        role, content = item.get("role"), str(item.get("content", ""))[:3000]
        if role in ("user", "assistant") and content:
            previous.append(f"{'Utilisateur' if role == 'user' else 'Assistant'} : {content}")
    if previous:
        messages.append({"role": "user", "content": (
            f"{HISTORY_PREFIX}\n\n" + "\n\n".join(previous) + "\n\n"
            "Tiens compte de ces échanges pour accomplir la tâche ci-dessus.")})
    return messages


def _tool_call_dicts(calls) -> list[dict]:
    out = []
    for call in calls or []:
        fn = field(call, "function", {})
        args = field(fn, "arguments", {})
        out.append({"function": {"name": field(fn, "name", ""), "arguments": dict(args) if args else {}}})
    return out


# --------------------------------------------------------------------------- Dynatrace sub-agent

# The MCP tools (Dynatrace) are not given to the main agent: it delegates to a specialised sub-agent that has
# its own instruction, its own context and only the MCP tools. The main agent just sees one tool, ask_dynatrace,
# and a short summary, so its context stays small. Set MCP_SUBAGENT=false to give the MCP tools directly.
SUBAGENT = os.getenv("MCP_SUBAGENT", "true").strip().lower() in ("1", "true", "y", "yes", "on")
DT_MAX_STEPS = int(os.getenv("DT_AGENT_MAX_STEPS", "4"))

ASK_DYNATRACE = {"type": "function", "function": {
    "name": "ask_dynatrace",
    "description": "Delegate a question about the user's Dynatrace environment (problems, logs, metrics, spans, "
                   "entities, DQL) to the Dynatrace specialist sub-agent. It queries the platform (MCP tools, dtctl) "
                   "and returns a short factual summary. Ask a complete, self-contained question.",
    "parameters": {"type": "object", "required": ["question"], "properties": {
        "question": {"type": "string", "description": "The question to answer from the Dynatrace environment"}}}}}

DT_BASE_PROMPT = (
    "You are a Dynatrace specialist sub-agent. You answer a question about a Dynatrace environment by calling "
    "your tools (MCP). Rules: get facts from the tools, never invent data; if a tool can generate a DQL query "
    "from natural language, use it first, then execute the query; always limit the volume (for example "
    "'| limit 20', few fields, a short time range); make as few calls as possible. Your final answer is a concise "
    "factual summary (150 words at most) in the language of the question, with the key figures, entity names, "
    "ids and the time range. When a tool returns several items (problems, entities, log lines...), list EVERY item "
    "returned (id and title), up to 15, before summarizing: never keep only the first. If the result says it was "
    "truncated, say that the list may be incomplete. If a tool fails or returns nothing, say so plainly instead "
    "of guessing."
)


def dynatrace_tool_schemas() -> list[dict]:
    """Tools of the Dynatrace side: MCP tools, dtctl (read-only CLI) and skills (know-how). Skills alone are not
    enough: they only help when there is a way to query the platform."""
    tools = mcp_tools.tool_schemas() + ([dtctl_tool.SCHEMA] if dtctl_tool.available() else [])
    return (tools + skills.schemas()) if tools else []


def dt_system_prompt() -> str:
    """Sub-agent instruction, completed with what the participants set up (dtctl, skills)."""
    extra = ""
    if dtctl_tool.available():
        extra += ("\n\nYou also have a `dtctl` tool (read-only Dynatrace CLI): run 'commands' to discover what exists, "
                  "`exec copilot nl2dql \"<question>\"` turns a question into DQL, `query \"<DQL>\"` runs a query.")
    return DT_BASE_PROMPT + extra + skills.prompt_section()


def subagent_active() -> bool:
    """True when the Dynatrace tools are reached through the Dynatrace sub-agent."""
    return SUBAGENT and bool(dynatrace_tool_schemas())


# --------------------------------------------------------------------------- the agents

def agent_turn(req, queue: asyncio.Queue, sse):
    """Build the traced agent run for one request. Events go to `queue` as SSE strings.

    Traces:  agent.run > agent.step (LLM) / <tool> ... ;  with MCP: ask_dynatrace (@tool) > dynatrace_agent
    (@agent) > agent.step (LLM) / <mcp tool> ...
    """
    totals = {"steps": 0, "tokens": 0, "tps": 0.0}
    sampling = {"temperature": req.temperature, "top_k": req.top_k, "top_p": req.top_p, "num_ctx": NUM_CTX}

    async def loop(messages: list[dict], tools: list[dict], max_steps: int, who: str, run_one) -> str:
        """Tool-calling loop shared by the main agent and the sub-agent; returns the final answer.
        `who` labels the events for the web UI ("main" or "dynatrace")."""
        final = ""
        for step in range(1, max_steps + 1):
            use_tools = bool(tools) and step < max_steps      # last step : no tools, the model must answer
            await queue.put(sse("step", {"n": step, "agent": who}))

            @task("agent.step")
            async def think() -> dict:
                content, calls = [], []
                stream = await rag._client.chat(
                    model=req.model or rag.LLM_MODEL, messages=messages, tools=tools if use_tools else None,
                    stream=True, options=sampling)
                async for part in stream:
                    msg = field(part, "message", {})
                    text = field(msg, "content", "")
                    if text:
                        content.append(text)
                        await queue.put(sse("token", {"text": text, "agent": who}))
                    calls.extend(field(msg, "tool_calls", []) or [])
                    if field(part, "done", False):
                        used_prompt = field(part, "prompt_eval_count", 0)
                        if field(part, "done_reason", "") == "length":
                            await queue.put(sse("warning", {"code": "length", "ctx": NUM_CTX, "agent": who}))
                        elif used_prompt >= 0.9 * NUM_CTX:
                            await queue.put(sse("warning", {"code": "context", "tokens": used_prompt,
                                                            "ctx": NUM_CTX, "agent": who}))
                        n = field(part, "eval_count", 0)
                        duration = field(part, "eval_duration", 0) / 1e9
                        totals["tokens"] += n
                        if duration:
                            totals["tps"] = round(n / duration, 2)
                return {"content": "".join(content), "tool_calls": _tool_call_dicts(calls)}

            reply = await think()
            totals["steps"] += 1
            if not reply["tool_calls"]:
                final = reply["content"]
                break

            messages.append({"role": "assistant", "content": reply["content"], "tool_calls": reply["tool_calls"]})
            for call in reply["tool_calls"]:
                name, args = call["function"]["name"], call["function"]["arguments"]
                await queue.put(sse("tool_call", {"name": name, "args": args, "agent": who}))
                result = await run_one(name, args)
                await queue.put(sse("tool_result", {"name": name, "result": result, "agent": who}))
                messages.append({"role": "tool", "tool_name": name, "content": result})
        return final

    @tool("ask_dynatrace")
    async def ask_dynatrace(question: str) -> str:
        @agent("dynatrace_agent")
        async def dynatrace_agent(task_text: str) -> str:
            messages = [{"role": "user", "content": task_text}, {"role": "system", "content": dt_system_prompt()}]
            return await loop(messages, dynatrace_tool_schemas(), DT_MAX_STEPS, "dynatrace", run_tool)

        answer = await dynatrace_agent(question)
        return clip(answer or "Le sous-agent Dynatrace n'a pas produit de réponse.")

    async def main_tool(name: str, args: dict) -> str:
        if name == "ask_dynatrace":
            try:
                return await ask_dynatrace(str(args.get("question", "")))
            except Exception as exc:
                log.exception("dynatrace sub-agent failed")
                return f"Erreur du sous-agent Dynatrace : {exc}"
        return await run_tool(name, args)

    @agent("agent.run")
    async def run(task_text: str) -> str:
        messages = build_agent_messages(task_text, req.history, req.system_prompt)
        await mcp_tools.refresh()             # picks up the mcp.json created or edited by the participant
        tools = TOOLS + ([ASK_DYNATRACE] if subagent_active() else dynatrace_tool_schemas())
        return await loop(messages, tools, req.max_steps, "main", main_tool)

    return run, totals
