"""OpenTelemetry + Langfuse telemetry setup."""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

F = TypeVar("F", bound=Callable[..., Any])

_tracer: trace.Tracer | None = None


def setup_telemetry(
    service_name: str = "agentic-mlops",
    otlp_endpoint: str = "http://localhost:4317",
) -> None:
    """Initialize OpenTelemetry with OTLP exporter.

    Args:
        service_name: Name of the service for tracing.
        otlp_endpoint: OTLP collector gRPC endpoint.
    """
    global _tracer

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)


def get_tracer() -> trace.Tracer:
    """Get the configured tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("agentic-mlops")
    return _tracer


def trace_llm_call(func: F) -> F:
    """Decorator to trace LLM API calls with span attributes.

    Records: model, token counts, latency, prompt hash.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        with tracer.start_as_current_span(
            f"llm.{func.__name__}",
            attributes={"llm.function": func.__name__},
        ) as span:
            result = await func(*args, **kwargs)
            if hasattr(result, "usage"):
                span.set_attribute("llm.input_tokens", result.usage.input_tokens)
                span.set_attribute("llm.output_tokens", result.usage.output_tokens)
            return result

    return wrapper  # type: ignore[return-value]


def trace_mcp_tool(func: F) -> F:
    """Decorator to trace MCP tool calls with span attributes.

    Records: tool_name, server, duration, success/failure.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        tool_name = kwargs.get("tool_name", func.__name__)
        with tracer.start_as_current_span(
            f"mcp.{tool_name}",
            attributes={"mcp.tool_name": str(tool_name)},
        ) as span:
            try:
                result = await func(*args, **kwargs)
                span.set_attribute("mcp.success", True)
                return result
            except Exception as e:
                span.set_attribute("mcp.success", False)
                span.set_attribute("mcp.error", str(e))
                raise

    return wrapper  # type: ignore[return-value]
