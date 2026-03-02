from opentelemetry.environment_variables import OTEL_METRICS_EXPORTER, OTEL_TRACES_EXPORTER
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider

from unstructured_platform_plugins.etl_uvicorn.otel import (
    get_metric_provider,
    get_settings,
    get_trace_provider,
)


def test_get_settings_filters_none_from_traces(monkeypatch):
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "none")
    settings = get_settings()
    assert settings["trace_exporters"] == []


def test_get_settings_filters_none_from_metrics(monkeypatch):
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, "none")
    settings = get_settings()
    assert settings["metric_exporters"] == []


def test_get_settings_filters_none_from_combined_trace_exporters(monkeypatch):
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "none,console")
    settings = get_settings()
    assert settings["trace_exporters"] == ["console"]


def test_get_settings_filters_none_from_combined_metric_exporters(monkeypatch):
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, "none,console")
    settings = get_settings()
    assert settings["metric_exporters"] == ["console"]


def test_get_trace_provider_returns_none_when_exporter_is_none(monkeypatch):
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "none")
    assert get_trace_provider() is None


def test_get_metric_provider_returns_none_when_exporter_is_none(monkeypatch):
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, "none")
    assert get_metric_provider() is None


def test_get_trace_provider_returns_provider_when_exporter_set(monkeypatch):
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "console")
    provider = get_trace_provider()
    assert isinstance(provider, TracerProvider)


def test_get_metric_provider_returns_provider_when_exporter_set(monkeypatch):
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, "console")
    provider = get_metric_provider()
    assert isinstance(provider, MeterProvider)


def test_wrap_in_fastapi_does_not_crash_with_none_otel_exporters(monkeypatch):
    """Regression: previously crashed with NotImplementedError when none was set."""
    monkeypatch.setenv(OTEL_TRACES_EXPORTER, "none")
    monkeypatch.setenv(OTEL_METRICS_EXPORTER, "none")

    from test.assets.async_typed_dict_response import async_sample_function
    from unstructured_platform_plugins.etl_uvicorn.api_generator import wrap_in_fastapi

    # Should not raise NotImplementedError
    app = wrap_in_fastapi(func=async_sample_function, plugin_id="test_plugin")
    assert app is not None
