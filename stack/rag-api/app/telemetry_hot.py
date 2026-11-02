"""Telemetry type switchable at runtime (TELEMETRY_SWITCH=true): OpenLLMetry <-> OpenInference, without restarting.

Both Ollama instrumentations stay installed for the whole life of the process (OpenLLMetry's own uninstrument() does
not undo its patch, so it cannot be toggled). What is toggled is the tracer they receive: a "gated" provider hands out
the real tracer when its type is the active one and a no-op tracer otherwise. Only the active type produces spans:
  - openllmetry   : opentelemetry-instrumentation-ollama + traceloop.* spans  -> Dynatrace OTLP directly
  - openinference : OpenInference OllamaInstrumentor + openinference.* spans  -> OpenTelemetry Collector -> Dynatrace
Each type has its own tracer provider (exporter, history masking), so switching is just changing `_state["active"]`.
Prototype limit: the OpenLLMetry metrics (token usage, duration) of the Traceloop SDK are not reproduced.
"""
import contextlib
import logging
import os
import socket
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app import telemetry_openinference as oi
from app.telemetry import TYPES, _auth_header, _strip_history, _truthy

log = logging.getLogger("telemetry")
_state = {"active": ""}
_providers: dict = {}
_NOOP = trace.NoOpTracer()


class _GatedTracer(trace.Tracer):
    """Real tracer while `kind` is the active type, no-op tracer otherwise (the instrumentation code then does nothing)."""

    def __init__(self, kind: str, real):
        self._kind, self._real = kind, real

    def _pick(self):
        return self._real if _state["active"] == self._kind else _NOOP

    def start_span(self, *args, **kwargs):
        return self._pick().start_span(*args, **kwargs)

    @contextlib.contextmanager
    def start_as_current_span(self, *args, **kwargs):
        with self._pick().start_as_current_span(*args, **kwargs) as span:
            yield span


class _GatedProvider(trace.TracerProvider):
    def __init__(self, kind: str, real: TracerProvider):
        self._kind, self._real = kind, real

    def get_tracer(self, *args, **kwargs):
        return _GatedTracer(self._kind, self._real.get_tracer(*args, **kwargs))


class _OpenLLMetryStrip(SpanProcessor):
    """Same history / RAG masking as the Traceloop span_postprocess_callback (gen_ai.prompt.* attributes)."""

    def on_end(self, span) -> None:
        attrs = getattr(span, "_attributes", None)
        if getattr(attrs, "_immutable", False):  # the SDK locks the attributes of an ended span
            attrs._immutable = False
        _strip_history(span)


def active() -> str:
    return _state["active"]


def _collector_address() -> tuple:
    url = urlparse(os.getenv("OTEL_COLLECTOR_ENDPOINT", "http://otel-collector:4318"))
    return url.hostname, url.port or 4318


def switch(kind: str) -> str:
    """Make `kind` the active type. ValueError: unknown type. RuntimeError: OpenInference selected but no collector."""
    if kind not in TYPES:
        raise ValueError(f"unknown telemetry type {kind!r}")
    if kind == "openinference":
        try:
            socket.create_connection(_collector_address(), timeout=2).close()
        except OSError as exc:
            raise RuntimeError("the OpenTelemetry Collector is unreachable (COMPOSE_PROFILES=openinference, "
                               f"service otel-collector): {exc}") from exc
    _state["active"] = kind
    log.info("telemetry type switched to %s", kind)
    return kind


def init(initial: str, service_name: str, tenant: str, token: str) -> None:
    """Install both instrumentations; `initial` is the active type. Must run before ollama / chromadb are imported."""
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.ollama import OllamaInstrumentor as OpenInferenceOllama
    from opentelemetry.instrumentation.ollama import OllamaInstrumentor as OpenLLMetryOllama

    trace_content = _truthy(os.getenv("OPENLLMETRY_TRACE_CONTENT", "true"))
    os.environ["TRACELOOP_TRACE_CONTENT"] = "true" if trace_content else "false"   # read by the OpenLLMetry instrumentation
    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": "ai-training",
        "host.name": os.getenv("VM_FQDN", "localhost"),
    })

    direct = TracerProvider(resource=resource)
    direct.add_span_processor(_OpenLLMetryStrip())   # before the exporter: the span is modified in place
    direct.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"https://{tenant}/api/v2/otlp/v1/traces", headers=_auth_header(token)),
        schedule_delay_millis=1000))

    collector_host, collector_port = _collector_address()
    through_collector = TracerProvider(resource=resource)
    through_collector.add_span_processor(oi.StripHistoryProcessor())
    through_collector.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"http://{collector_host}:{collector_port}/v1/traces"), schedule_delay_millis=1000))

    _providers.update({"openllmetry": direct, "openinference": through_collector})
    _state["active"] = initial

    OpenLLMetryOllama().instrument(tracer_provider=_GatedProvider("openllmetry", direct))
    hide = not trace_content
    OpenInferenceOllama().instrument(
        tracer_provider=_GatedProvider("openinference", through_collector),
        config=TraceConfig(hide_inputs=hide, hide_outputs=hide, hide_input_messages=hide, hide_output_messages=hide))
    log.info("telemetry hot switch ready: service %s, active type %s", service_name, initial)


def decorator(kind: str, name: str):
    """@workflow / @task / @agent / @tool as spans of the active type (chosen at each call)."""
    def get_tracer():
        return _providers[_state["active"]].get_tracer("ai-lab")

    def get_attributes():
        if _state["active"] == "openinference":
            return oi._default_attributes(kind, name)
        return {"traceloop.span.kind": kind, "traceloop.entity.name": name}

    return oi.decorator(kind, name, get_tracer=get_tracer, get_attributes=get_attributes)
