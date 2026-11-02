"""OpenInference (Arize) -> OpenTelemetry Collector -> Dynatrace AI Observability, selected with TELEMETRY_TYPE=openinference.

Follows https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples/tree/main/ollama/openinference :
  - a TracerProvider exports the spans in OTLP/HTTP to the collector (OTEL_COLLECTOR_ENDPOINT, no credential here),
  - OllamaInstrumentor produces the LLM span (model, parameters, token usage, prompt and completion) with the
    OpenInference attributes (llm.*),
  - the collector (otel-collector/otel-collector-config.yaml) converts them to the gen_ai.* conventions that
    Dynatrace understands, derives the gen_ai.client.* metrics and forwards everything to the tenant.
The application activity (chat: rag.chat, rag.retrieve, rag.generate - agent: agent.run, agent.step, one span per tool)
is made of plain spans with the openinference.span.kind attribute (CHAIN, AGENT, TOOL), see decorator().
A span processor removes the conversation history and the RAG passages from the exported prompt (same rule as OpenLLMetry).
"""
import functools
import inspect
import json
import logging
import os
import re

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.telemetry import _is_stripped, _truthy

log = logging.getLogger("telemetry")

SPAN_KIND = "openinference.span.kind"
KINDS = {"workflow": "CHAIN", "task": "CHAIN", "agent": "AGENT", "tool": "TOOL"}
MAX_VALUE = 2000   # characters kept from the input / output of an application span


def _trace_content() -> bool:
    return _truthy(os.getenv("OPENLLMETRY_TRACE_CONTENT", "true"))


class StripHistoryProcessor(SpanProcessor):
    """Drop the history and RAG messages (llm.input_messages.<i>.message.*) from the prompt recorded on the LLM span.

    Token usage is left untouched: the model really did receive these messages.
    input.value (the whole request, as JSON) would give them back, so it is removed when something was stripped.
    """

    PREFIX = "llm.input_messages."

    def on_end(self, span) -> None:
        try:
            attrs = span._attributes
            indexed = {}
            for key in list(attrs.keys()):
                m = re.match(re.escape(self.PREFIX) + r"(\d+)\.(.+)$", key)
                if m:
                    indexed.setdefault(int(m.group(1)), {})[m.group(2)] = attrs[key]
            if not any(_is_stripped(f.get("message.content", "")) for f in indexed.values()):
                return
            if getattr(attrs, "_immutable", False):  # the SDK locks the attributes of an ended span
                attrs._immutable = False
            for key in list(attrs.keys()):
                if key.startswith(self.PREFIX):
                    del attrs[key]
            kept = [f for _, f in sorted(indexed.items()) if not _is_stripped(f.get("message.content", ""))]
            for i, fields in enumerate(kept):
                for name, value in fields.items():
                    attrs[f"{self.PREFIX}{i}.{name}"] = value
            if "input.value" in attrs:
                del attrs["input.value"]
        except Exception:  # never break the export
            log.exception("could not strip history from the LLM span")


def init(service_name: str) -> None:
    """Set up the tracer provider and the Ollama instrumentation. Must run before ollama / chromadb are imported."""
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.ollama import OllamaInstrumentor

    endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT", "http://otel-collector:4318").rstrip("/")
    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "ai-training",
        "host.name": os.getenv("VM_FQDN", "localhost"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(StripHistoryProcessor())   # before the exporter: the span is modified in place
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"), schedule_delay_millis=1000))
    trace.set_tracer_provider(provider)

    # prompts and completions are recorded unless explicitly turned off
    hide = not _trace_content()
    config = TraceConfig(hide_inputs=hide, hide_outputs=hide, hide_input_messages=hide, hide_output_messages=hide)
    OllamaInstrumentor().instrument(tracer_provider=provider, config=config)
    log.info("OpenInference enabled: service %s -> collector %s (trace content: %s)", service_name, endpoint, not hide)


def _short(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)[:MAX_VALUE]


def _default_attributes(kind: str, name: str) -> dict:
    attributes = {SPAN_KIND: KINDS[kind]}
    if KINDS[kind] == "TOOL":
        attributes["tool.name"] = name
    return attributes


def decorator(kind: str, name: str, get_tracer=None, get_attributes=None):
    """Span around a function (sync or async), the equivalent of Traceloop's @workflow / @task / @agent / @tool.

    get_tracer / get_attributes are called at each call: the hot-switch mode (telemetry_hot.py) uses them to follow
    the type selected at that moment.
    """
    def start():
        tracer = get_tracer() if get_tracer else trace.get_tracer("ai-lab")
        attributes = get_attributes() if get_attributes else _default_attributes(kind, name)
        return tracer.start_as_current_span(name, attributes=attributes)

    def record_input(span, args, kwargs):
        if _trace_content() and (args or kwargs):
            span.set_attribute("input.value", _short({"args": args, "kwargs": kwargs}))

    def record_output(span, result):
        if _trace_content() and result is not None:
            span.set_attribute("output.value", _short(result))

    def wrap(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                with start() as span:
                    record_input(span, args, kwargs)
                    result = await fn(*args, **kwargs)
                    record_output(span, result)
                    return result
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with start() as span:
                record_input(span, args, kwargs)
                result = fn(*args, **kwargs)
                record_output(span, result)
                return result
        return wrapper

    return wrap
