import os
from typing import Literal, TypedDict

from opentelemetry.environment_variables import OTEL_METRICS_EXPORTER, OTEL_TRACES_EXPORTER
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

TraceExporterType = Literal["otlp", "jaeger", "zipkin", "console"]
MetricExporterType = Literal["otlp", "prometheus", "none"]


class OtelSettings(TypedDict):
    service_name: str
    trace_exporters: list[TraceExporterType]
    metric_exporters: list[MetricExporterType]


def get_settings() -> OtelSettings:
    service_name = os.environ.get(OTEL_SERVICE_NAME, "unknown_service")
    trace_exporters = os.environ.get(OTEL_TRACES_EXPORTER)
    trace_exporters = trace_exporters.split(",") if trace_exporters else []

    metric_exporters = os.environ.get(OTEL_METRICS_EXPORTER)
    metric_exporters = metric_exporters.split(",") if metric_exporters else []
    return OtelSettings(
        service_name=service_name,
        trace_exporters=trace_exporters,
        metric_exporters=metric_exporters,
    )


def get_trace_provider() -> TracerProvider:
    settings = get_settings()
    provider = TracerProvider(resource=Resource({SERVICE_NAME: settings["service_name"]}))

    for trace_exporter_type in settings["trace_exporters"]:
        _add_trace_exporter(exporter_type=trace_exporter_type, provider=provider)

    return provider


def get_metric_provider() -> MeterProvider:
    settings = get_settings()
    readers = []
    for metric_exporter_type in settings["metric_exporters"]:
        readers.append(_get_metrics_reader(exporter_type=metric_exporter_type))
    return MeterProvider(
        resource=Resource({SERVICE_NAME: settings["service_name"]}), metric_readers=readers
    )


def _add_trace_exporter(exporter_type: TraceExporterType, provider: TracerProvider):
    if exporter_type == "otlp":
        _add_traces_otlp_exporter(
            provider,
        )

    elif exporter_type == "console":
        _add_traces_console_exporter(provider)
    else:
        raise NotImplementedError(f"{exporter_type} implementation not supported yet")


def _get_metrics_reader(exporter_type: MetricExporterType) -> MetricReader:
    if exporter_type == "otlp":
        return _get_metric_otlp_reader()
    if exporter_type == "console":
        return _get_metric_console_reader()
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


def _get_metric_otlp_reader() -> MetricReader:
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    exporter = OTLPMetricExporter()
    return PeriodicExportingMetricReader(exporter)


def _get_metric_console_reader() -> MetricReader:
    exporter = ConsoleMetricExporter()
    return PeriodicExportingMetricReader(exporter)
