from __future__ import annotations

import pytest
from utic_invocation_settings import (
    Blame,
    DecryptionError,
    IdentityNotMountedError,
    KeyNotFoundError,
    MalformedDagNodeSettingsError,
    MalformedEnvelopeError,
    SealedDagNodeSettingsRequiredError,
)

from unstructured_platform_plugins.invocation_context import (
    RESERVED_CONTEXT_KEY,
    InvocationContext,
    UnsupportedContextVersionError,
    dimensions,
    extract_context,
)
from unstructured_platform_plugins.invocation_settings import http_status_for

VALID = {
    "schema_version": "1",
    "invocation_id": "inv-1",
    "job_id": "job-1",
    "tenant_id": "tenant-1",
    "dag_node_id": "node-1",
    "dag_node_type": "chunker",
    "record_id": "rec-1",
    "attempt": 2,
}


def test_extracts_identity_fields_from_body():
    context = extract_context({"file_data": {"path": "x"}, RESERVED_CONTEXT_KEY: VALID})
    assert context is not None
    assert context.tenant_id == "tenant-1"
    assert context.attempt == 2


def test_absent_key_returns_none():
    assert extract_context({"file_data": {"path": "x"}}) is None


def test_accepts_already_parsed():
    context = InvocationContext(**VALID)
    assert extract_context({RESERVED_CONTEXT_KEY: context}) is context


def test_present_but_null_fails_closed():
    # Same rule as the envelope: a context that silently vanishes takes tenant attribution with it.
    with pytest.raises(MalformedEnvelopeError):
        extract_context({RESERVED_CONTEXT_KEY: None})


def test_present_but_not_an_object_fails_closed():
    with pytest.raises(MalformedEnvelopeError):
        extract_context({RESERVED_CONTEXT_KEY: "tenant-1"})


def test_unknown_schema_version_is_rejected_by_its_own_error():
    with pytest.raises(UnsupportedContextVersionError) as exc:
        extract_context({RESERVED_CONTEXT_KEY: {**VALID, "schema_version": "2"}})
    assert "'2'" in str(exc.value)


@pytest.mark.parametrize("version", [None, 2, ["1"]])
def test_a_mistyped_schema_version_is_malformed_not_version_skew(version):
    # Only a well-typed version string this consumer does not know reads as deployment skew;
    # a wrong-typed field is the caller's malformed context like any other field.
    with pytest.raises(MalformedEnvelopeError):
        extract_context({RESERVED_CONTEXT_KEY: {**VALID, "schema_version": version}})


def test_misaligned_batch_lists_are_rejected():
    # invocation_ids is read positionally against record_ids, so a length mismatch would let
    # every id past the gap name the wrong record.
    with pytest.raises(MalformedEnvelopeError):
        extract_context(
            {
                RESERVED_CONTEXT_KEY: {
                    **VALID,
                    "record_ids": ["r1", "r2"],
                    "invocation_ids": ["inv-1"],
                }
            }
        )


def test_partial_context_is_accepted():
    # A producer that populates only some identity facets degrades to less telemetry, not a
    # failed invoke.
    context = extract_context({RESERVED_CONTEXT_KEY: {"schema_version": "1", "job_id": "job-1"}})
    assert context is not None
    assert context.job_id == "job-1"
    assert context.tenant_id is None


def test_unknown_fields_survive_for_forward_compatibility():
    context = extract_context({RESERVED_CONTEXT_KEY: {**VALID, "future_field": "keep me"}})
    assert context is not None
    assert context.model_extra["future_field"] == "keep me"


def test_batch_fields_are_index_aligned():
    # The controller emits one invocation id per record, using None where a record carried no
    # context, so entry i always describes record i.
    context = extract_context(
        {
            RESERVED_CONTEXT_KEY: {
                **VALID,
                "record_ids": ["rec-1", "rec-2", "rec-3"],
                "invocation_ids": ["inv-1", None, "inv-3"],
            }
        }
    )
    assert context is not None
    assert len(context.record_ids) == len(context.invocation_ids)
    assert dict(zip(context.record_ids, context.invocation_ids))["rec-2"] is None


class TestDimensions:
    def test_returns_populated_identity_facets(self):
        context = InvocationContext(**VALID)

        assert dimensions(context) == {
            "invocation_id": "inv-1",
            "job_id": "job-1",
            "tenant_id": "tenant-1",
            "dag_node_id": "node-1",
            "dag_node_type": "chunker",
            "record_id": "rec-1",
            "attempt": 2,
        }

    def test_excludes_batch_fields(self):
        # These describe the work, not who it belongs to, and would blow up dimension cardinality.
        context = InvocationContext.model_validate(
            {**VALID, "record_ids": ["a"], "invocation_ids": ["b"]}
        )

        assert not {"record_ids", "invocation_ids"} & set(dimensions(context))

    def test_unknown_producer_fields_are_not_promoted_to_dimensions(self):
        context = InvocationContext.model_validate({**VALID, "future_field": "value"})

        assert "future_field" not in dimensions(context)

    def test_absent_context_yields_no_dimensions(self):
        assert dimensions(None) == {}


class TestHttpStatusFor:
    """The transport's spelling of the library's normative `blame` -> status rule."""

    def test_caller_blame_is_the_only_422(self):
        assert http_status_for(MalformedEnvelopeError("x")) == 422
        assert MalformedEnvelopeError.blame is Blame.CALLER

    @pytest.mark.parametrize(
        "error",
        [
            DecryptionError("x"),
            KeyNotFoundError("x"),
            IdentityNotMountedError("x"),
            SealedDagNodeSettingsRequiredError("x"),
            MalformedDagNodeSettingsError("x"),
            UnsupportedContextVersionError("x"),
        ],
    )
    def test_everything_else_is_5xx(self, error):
        assert http_status_for(error) == 500

    def test_an_unclassified_exception_is_not_blamed_on_the_caller(self):
        assert http_status_for(RuntimeError("boom")) == 500
