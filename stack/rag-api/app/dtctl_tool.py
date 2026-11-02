"""dtctl (Dynatrace CLI) as a tool of the Dynatrace sub-agent.

The binary is installed in the image (see rag-api/Dockerfile). The participants configure it themselves from the
VS Code web terminal (see stack/mcp/README.md): `dtctl config set-context ... --safety-level readonly` and
`dtctl config set-credentials ...` write DTCTL_CONFIG, which is shared with this container.

Safety: the agent only gets a read-only subset of commands (allow-list of verbs, no way to change the configuration,
the context, the credentials or to read local files). dtctl's own safety level is enforced client side only: the
real protection is a token with read-only scopes.
"""
import asyncio
import json
import logging
import os
import shlex
import shutil

from app.limits import clip, compact

log = logging.getLogger("dtctl")

DTCTL_BIN = os.getenv("DTCTL_BIN", "dtctl")
DTCTL_CONFIG = os.getenv("DTCTL_CONFIG", "/workspace/mcp/dtctl-config")
TIMEOUT_S = int(os.getenv("DTCTL_TIMEOUT", "60"))
MAX_OUTPUT_TOKENS = os.getenv("DTCTL_MAX_OUTPUT_TOKENS", "1200")

READ_VERBS = {"query", "get", "describe", "logs", "inventory", "commands", "inspect", "doctor", "version"}
COPILOT_ACTIONS = {"nl2dql", "dql2nl"}
# flags that would let the model change the target, the credentials, read local files or run forever
BLOCKED_FLAGS = {"--config", "--context", "--token", "--environment", "--insecure", "-f", "--file",
                 "--watch", "-w", "--output-file", "--spill-dir"}

SCHEMA = {"type": "function", "function": {
    "name": "dtctl",
    "description": "Run one read-only dtctl command (Dynatrace CLI) against the user's Dynatrace environment and "
                   "return its JSON output. Pass everything after 'dtctl' as `command`. Examples: "
                   "query \"fetch logs | filter loglevel == \\\"ERROR\\\" | limit 20\" ; "
                   "exec copilot nl2dql \"error logs from the last hour\" ; inventory ; commands. "
                   "Use 'commands' to discover what exists, always limit the results.",
    "parameters": {"type": "object", "required": ["command"], "properties": {
        "command": {"type": "string", "description": "The dtctl arguments, without the word dtctl"}}}}}


def installed() -> bool:
    return bool(shutil.which(DTCTL_BIN)) or os.path.isfile(DTCTL_BIN)


def configured() -> bool:
    return os.path.isfile(DTCTL_CONFIG)


def available() -> bool:
    """True when the tool can be offered to the agent (binary installed and configured by the participant)."""
    return installed() and configured()


def status() -> dict:
    return {"installed": installed(), "configured": configured(), "config": DTCTL_CONFIG}


def check(args: list[str]) -> str:
    """Return an error message if the command is not allowed, '' otherwise."""
    if not args:
        return "commande vide"
    if args[0] == "exec":
        if len(args) < 3 or args[1] != "copilot" or args[2] not in COPILOT_ACTIONS:
            return "seul « exec copilot nl2dql|dql2nl » est autorisé parmi les commandes exec"
    elif args[0] not in READ_VERBS:
        return f"commande « {args[0]} » non autorisée (lecture seule : {', '.join(sorted(READ_VERBS))}, exec copilot)"
    for a in args:
        flag = a.split("=", 1)[0]
        if flag in BLOCKED_FLAGS:
            return f"option « {flag} » non autorisée"
    return ""


def _format(stdout: str, stderr: str, code: int) -> str:
    text = stdout.strip()
    try:
        env = json.loads(text)
    except ValueError:
        env = None
    if isinstance(env, dict) and env.get("ok") is False:
        err = env.get("error") or {}
        out = f"Erreur dtctl [{err.get('code', 'error')}] : {err.get('message', '')}"
        if err.get("suggestions"):
            out += " Suggestions : " + "; ".join(map(str, err["suggestions"]))[:500]
        return out
    if code != 0 and not text:
        return f"Erreur dtctl (code {code}) : {stderr.strip()[:800] or 'aucune sortie'}"
    return text or stderr.strip() or "(sortie vide)"


async def _exec(args: list[str], extra: list[str]) -> tuple[str, str, int]:
    env = {k: v for k, v in os.environ.items() if v != "" or not k.startswith("DTCTL_")}
    env.update(DTCTL_CONFIG=DTCTL_CONFIG, DTCTL_SPILL="never", NO_COLOR="1")
    proc = await asyncio.create_subprocess_exec(
        DTCTL_BIN, *args, *extra, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "", f"délai dépassé ({TIMEOUT_S} s)", 124
    return out.decode("utf-8", "replace"), err.decode("utf-8", "replace"), proc.returncode


async def run(command: str) -> str:
    """Run one dtctl command (agent mode, bounded output); errors come back as text for the model."""
    if not installed():
        return "Erreur : dtctl n'est pas installé dans cette image."
    if not configured():
        return f"Erreur : dtctl n'est pas configuré ({DTCTL_CONFIG} introuvable). Voir stack/mcp/README.fr.md."
    try:
        args = shlex.split(str(command))
    except ValueError as exc:
        return f"Erreur : commande invalide ({exc})."
    if args and args[0] == "dtctl":
        args = args[1:]
    problem = check(args)
    if problem:
        return f"Erreur : {problem}."
    try:
        out, err, code = await _exec(args, ["--agent", "--max-output-tokens", MAX_OUTPUT_TOKENS])
        if code != 0 and "max-output-tokens" in err:       # a command without this flag: retry without it
            out, err, code = await _exec(args, ["--agent"])
    except OSError as exc:
        return f"Erreur : impossible de lancer dtctl ({exc})."
    return clip(compact(_format(out, err, code)))
