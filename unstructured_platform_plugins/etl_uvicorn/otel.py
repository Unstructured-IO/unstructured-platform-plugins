import os
from typing import Literal, TypedDict

from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

ExporterType = Literal["otlp", "jaeger", "zipkin", "console"]


class OtelSettings(TypedDict):
    service_name: str
    exporters: list[ExporterType]


def get_settings() -> OtelSettings:
    service_name = os.environ.get(OTEL_SERVICE_NAME, "unknown_service")
    exporters = os.environ.get(OTEL_TRACES_EXPORTER)
    exporters = exporters.split(",") if exporters else []
    return OtelSettings(service_name=service_name, exporters=exporters)


def get_provider() -> TracerProvider:
    settings = get_settings()
    provider = TracerProvider(resource=Resource({SERVICE_NAME: settings["service_name"]}))

    for exporter_type in settings["exporters"]:
        _add_exporter(exporter_type=exporter_type, provider=provider)

    return provider


def _add_exporter(exporter_type: ExporterType, provider: TracerProvider):
    if exporter_type == "otlp":
        _add_traces_otlp_exporter(
            provider,
        )

    elif exporter_type == "console":
        _add_traces_console_exporter(provider)
    else:
        raise NotImplementedError(f"{exporter_type} implementation not supported yet")


def _add_traces_console_exporter(provider: TracerProvider) -> None:
    exporter = ConsoleSpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)


def _add_traces_otlp_exporter(provider: TracerProvider) -> None:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporter = OTLPSpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
