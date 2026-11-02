"""OpenLLMetry (Traceloop SDK) -> Dynatrace AI Observability, enabled only on demand.

Follows https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/openllmetry :
  - Traceloop.init(...) pointed at the tenant OTLP endpoint (disable_batch=True),
  - metrics temporality set to "delta",
  - @workflow / @task / @agent / @tool decorators for the application activity
    (chat: rag.chat, rag.retrieve, rag.generate - agent: agent.run, agent.step, one span per tool).
The LLM span (model, parameters, token usage, prompt and completion) is produced by the SDK's own
Ollama instrumentation: nothing is hand-written, except a span_postprocess_callback that removes the
conversation history and the RAG passages from the exported prompt. Other instrumentations (ChromaDB, HTTP...) are blocked.

TELEMETRY_TYPE selects the instrumentation: "openllmetry" (default, this file) or "openinference"
(telemetry_openinference.py: OpenInference spans sent to an OpenTelemetry Collector that converts them to gen_ai.*).
OPENLLMETRY_ENABLED stays the on/off switch of the telemetry, whatever the type.
"""
import json
import logging
import os
import re

# Forced (not setdefault) : these must not be changed by a stray environment variable.
os.environ["TRACELOOP_TELEMETRY"] = "false"                          # Traceloop's own usage statistics
os.environ["OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"] = "delta"   # required by Dynatrace

log = logging.getLogger("telemetry")
_enabled = False
_active = ""   # "openllmetry" or "openinference" once the telemetry is running, "" otherwise
_hot = False   # TELEMETRY_SWITCH: the type can be changed at runtime (telemetry_hot.py)
TYPES = ("openllmetry", "openinference")


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "y", "yes", "on")


def telemetry_type() -> str:
    """Requested instrumentation (TELEMETRY_TYPE): openllmetry (default) or openinference."""
    value = os.getenv("TELEMETRY_TYPE", "openllmetry").strip().lower() or "openllmetry"
    if value not in TYPES:
        log.warning("unknown TELEMETRY_TYPE %r: using openllmetry", value)
        return "openllmetry"
    return value


def active_type() -> str:
    """Instrumentation really running ("" when the telemetry is disabled)."""
    if not _enabled:
        return ""
    if _hot:
        from app import telemetry_hot
        return telemetry_hot.active()
    return _active


def switchable() -> bool:
    return _enabled and _hot


def switch_type(kind: str) -> str:
    """Change the telemetry type at runtime (only with TELEMETRY_SWITCH). ValueError / RuntimeError on refusal."""
    if not switchable():
        raise RuntimeError("telemetry disabled or TELEMETRY_SWITCH off")
    from app import telemetry_hot
    return telemetry_hot.switch(kind)


def source_file() -> str:
    """File that holds the telemetry setup, shown in the web UI (Observability tab)."""
    if _hot:
        return "telemetry_hot.py"
    return "telemetry_openinference.py" if telemetry_type() == "openinference" else "telemetry.py"


def _auth_header(token: str) -> dict:
    # classic access tokens (dt0c01.*) use "Api-Token", platform tokens (dt0s16.*) use "Bearer"
    scheme = "Api-Token" if token.startswith("dt0c01.") else "Bearer"
    return {"Authorization": f"{scheme} {token}"}


# Markers of the messages that carry the previous turns and the RAG passages (see rag.build_messages).
# They are sent to the model but removed from the exported LLM span, so Dynatrace only shows the
# current question and the system instruction.
HISTORY_PREFIX = "Échanges précédents :"
RAG_PREFIX = "Passages de documents :"
def _is_stripped(text) -> bool:
    """History is always removed from the exported prompt; the RAG passages too, unless OPENLLMETRY_KEEP_RAG is on
    (LLM-judge evaluations such as dt-evals need the retrieved context to judge faithfulness)."""
    prefixes = (HISTORY_PREFIX,) if _truthy(os.getenv("OPENLLMETRY_KEEP_RAG", "false")) else (HISTORY_PREFIX, RAG_PREFIX)
    return str(text).startswith(prefixes)


def _message_text(message) -> str:
    """Text of one message, whether `content` is a string or a list of GenAI `parts`."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    parts = message.get("parts") or content or []
    return "".join(p.get("content", "") for p in parts if isinstance(p, dict) and isinstance(p.get("content"), str))


def _strip_history(span) -> None:
    """span_postprocess_callback: drop the history and RAG messages from the prompt recorded on the LLM span.

    Handles both attribute layouts the Ollama instrumentation can use:
      gen_ai.prompt.<i>.role / .content   (indexed attributes)
      gen_ai.input.messages               (JSON list)
    Token usage is left untouched: the model really did receive these messages.
    """
    try:
        attrs = span._attributes
        raw = attrs.get("gen_ai.input.messages")
        if isinstance(raw, str):
            messages = json.loads(raw)
            kept = [m for m in messages if not _is_stripped(_message_text(m))]
            if len(kept) != len(messages):
                attrs["gen_ai.input.messages"] = json.dumps(kept, ensure_ascii=False)

        indexed = {}
        for key in list(attrs.keys()):
            m = re.match(r"gen_ai\.prompt\.(\d+)\.(.+)$", key)
            if m:
                indexed.setdefault(int(m.group(1)), {})[m.group(2)] = attrs[key]
        if any(_is_stripped(f.get("content", "")) for f in indexed.values()):
            for key in list(attrs.keys()):
                if key.startswith("gen_ai.prompt."):
                    del attrs[key]
            kept = [f for _, f in sorted(indexed.items()) if not _is_stripped(f.get("content", ""))]
            for i, fields in enumerate(kept):
                for name, value in fields.items():
                    attrs[f"gen_ai.prompt.{i}.{name}"] = value
    except Exception:  # never break the export
        log.exception("could not strip history from the LLM span")


def service_name() -> str:
    """Service name suffixed with the VM number taken from the host name.

    aitraining03.francecentral.cloudapp.azure.com -> ai-lab-rag-api-03 (no suffix if no digits).
    """
    base = os.getenv("OTEL_SERVICE_NAME", "ai-lab-rag-api")
    first_label = os.getenv("VM_FQDN", "").split(".")[0]
    number = re.search(r"(\d+)$", first_label)
    return f"{base}-{number.group(1)}" if number else base


def init_telemetry() -> bool:
    """Initialise the telemetry (OpenLLMetry or OpenInference) if enabled. Must be called before importing ollama / chromadb."""
    global _enabled, _active, _hot
    if not _truthy(os.getenv("OPENLLMETRY_ENABLED", "false")):
        log.info("telemetry disabled")
        return False

    tenant = os.getenv("DT_TENANT", "").strip().strip("/")
    token = os.getenv("DT_API_TOKEN", "").strip()
    if not tenant or not token:
        log.warning("telemetry enabled but DT_TENANT / DT_API_TOKEN missing: telemetry disabled")
        return False

    if _truthy(os.getenv("TELEMETRY_SWITCH", "false")):
        try:
            from app import telemetry_hot
            telemetry_hot.init(telemetry_type(), service_name(), tenant, token)
            _enabled, _hot = True, True
            return True
        except Exception:  # never prevent the app from starting
            log.exception("telemetry hot switch initialisation failed: telemetry disabled")
            _enabled, _hot = False, False
            return False

    if telemetry_type() == "openinference":
        try:
            from app import telemetry_openinference
            telemetry_openinference.init(service_name())
            _enabled, _active = True, "openinference"
            return True
        except Exception:  # never prevent the app from starting
            log.exception("OpenInference initialisation failed: telemetry disabled")
            _enabled, _active = False, ""
            return False

    # prompts and completions are recorded by the SDK unless explicitly turned off
    os.environ["TRACELOOP_TRACE_CONTENT"] = "true" if _truthy(os.getenv("OPENLLMETRY_TRACE_CONTENT", "true")) else "false"

    try:
        from traceloop.sdk import Traceloop

        kwargs = dict(
            app_name=service_name(),
            api_endpoint=f"https://{tenant}/api/v2/otlp",
            headers=_auth_header(token),
            disable_batch=True,
            span_postprocess_callback=_strip_history,
            resource_attributes={
                "deployment.environment": "ai-training",
                "host.name": os.getenv("VM_FQDN", "localhost"),
            },
        )
        try:
            # only the Ollama (LLM) instrumentation: block everything else
            from traceloop.sdk.instruments import Instruments
            kwargs.update(instruments={Instruments.OLLAMA})
        except Exception:
            log.warning("cannot restrict automatic instrumentations with this SDK version")

        try:
            Traceloop.init(**kwargs)
        except TypeError:  # older SDK without `instruments`
            kwargs.pop("instruments", None)
            kwargs.pop("span_postprocess_callback", None)
            Traceloop.init(**kwargs)

        _enabled, _active = True, "openllmetry"
        log.info("OpenLLMetry enabled: service %s -> %s (trace content: %s)", kwargs["app_name"],
                 kwargs["api_endpoint"], os.environ["TRACELOOP_TRACE_CONTENT"])
        return True
    except Exception:  # never prevent the app from starting
        log.exception("OpenLLMetry initialisation failed: telemetry disabled")
        _enabled, _active = False, ""
        return False


def is_enabled() -> bool:
    return _enabled


def _decorator(kind: str, name: str):
    """Traceloop @workflow / @task (or the OpenInference span equivalent) when enabled, otherwise a no-op decorator."""
    if not _enabled:
        return lambda fn: fn
    if _hot:
        from app import telemetry_hot
        return telemetry_hot.decorator(kind, name)
    if _active == "openinference":
        from app import telemetry_openinference
        return telemetry_openinference.decorator(kind, name)
    from traceloop.sdk import decorators
    return getattr(decorators, kind)(name=name)


def workflow(name: str):
    return _decorator("workflow", name)


def task(name: str):
    return _decorator("task", name)


def agent(name: str):
    return _decorator("agent", name)


def tool(name: str):
    return _decorator("tool", name)
