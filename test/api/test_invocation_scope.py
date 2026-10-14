import asyncio
from dataclasses import FrozenInstanceError, dataclass, fields
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from unstructured_platform_plugins import (
    InvocationIdentity,
    current_invocation_identity,
    invocation_scratch_dir,
)
from unstructured_platform_plugins.etl_uvicorn.api_generator import generate_fast_api
from unstructured_platform_plugins.invocation_context import InvocationContext
from unstructured_platform_plugins.invocation_settings import invocation_envelope


@pytest.mark.parametrize("bound", [False, True])
def test_identity_field_fallback(monkeypatch, bound):
    for field in fields(InvocationIdentity):
        monkeypatch.setenv(field.name.upper(), f"env-{field.name}")
    context = InvocationContext(job_id="request", tenant_id="") if bound else None
    with invocation_envelope(None, context):
        identity = current_invocation_identity()
    assert identity.job_id == ("request" if bound else "env-job_id")
    assert identity.tenant_id == ("" if bound else "env-tenant_id")
    assert identity.org_id == "env-org_id"
    with pytest.raises(FrozenInstanceError):
        identity.job_id = "other"


def test_absent_identity(monkeypatch):
    for field in fields(InvocationIdentity):
        monkeypatch.delenv(field.name.upper(), raising=False)
    assert all(
        getattr(current_invocation_identity(), f.name) is None for f in fields(InvocationIdentity)
    )


def test_boot_path_and_creation(tmp_path):
    root = tmp_path / "scratch"
    assert invocation_scratch_dir(root, create=False) == root
    assert not root.exists()
    assert invocation_scratch_dir(str(root)) == root
    assert root.is_dir()


@pytest.mark.parametrize("segment", ["../a", "..", ".", "a/b", "a\\b", "x" * 300, "☃"])
def test_segments_are_safe_and_bounded(tmp_path, segment):
    context = InvocationContext(job_id=segment, dag_node_id=segment, invocation_id=segment)
    with invocation_envelope(None, context):
        path = invocation_scratch_dir(tmp_path)
    assert path.is_relative_to(tmp_path)
    assert len(path.relative_to(tmp_path).parts) == 3
    assert all(p not in {".", ".."} and len(p) <= 96 for p in path.relative_to(tmp_path).parts)
    assert path.is_dir()


def test_sanitization_does_not_alias(tmp_path):
    paths = []
    for job_id in ["a/b", "a_b"]:
        with invocation_envelope(None, InvocationContext(job_id=job_id, invocation_id="invoke")):
            paths.append(invocation_scratch_dir(tmp_path, create=False))
    assert paths[0] != paths[1]


def test_single_record_and_batch_correlation(tmp_path):
    with invocation_envelope(
        None,
        InvocationContext(
            job_id="job", dag_node_id="node", invocation_id="invoke", record_id="record"
        ),
    ):
        assert invocation_scratch_dir(tmp_path, create=False) == tmp_path / "job/node/invoke"
    with invocation_envelope(None, InvocationContext(record_id="record")):
        assert invocation_scratch_dir(tmp_path, create=False).name == "record"
    with invocation_envelope(None, InvocationContext(invocation_id="", record_id="record")):
        assert invocation_scratch_dir(tmp_path, create=False).name == "record"
    with invocation_envelope(None, InvocationContext(record_id="record", record_ids=["record"])):
        first = invocation_scratch_dir(tmp_path, create=False)
        second = invocation_scratch_dir(tmp_path, create=False)
        assert first != second
        assert first.name != "record"


def test_concurrent_invocations_are_isolated(tmp_path):
    async def invoke(job):
        with invocation_envelope(
            None, InvocationContext(job_id=job, dag_node_id="node", invocation_id="invoke")
        ):
            await asyncio.sleep(0)
            return current_invocation_identity().job_id, invocation_scratch_dir(tmp_path)

    async def run():
        return await asyncio.gather(invoke("one"), invoke("two"))

    results = asyncio.run(run())
    assert results == [("one", tmp_path / "one/node/invoke"), ("two", tmp_path / "two/node/invoke")]


@dataclass
class ScratchOutput:
    path: str


def test_streaming_retains_invocation_scope(tmp_path):
    async def stream() -> ScratchOutput:
        await asyncio.sleep(0)
        yield ScratchOutput(
            str(invocation_scratch_dir(tmp_path) / current_invocation_identity().job_id)
        )

    app = generate_fast_api(stream)
    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={
                "invocation_context": {
                    "job_id": "job",
                    "dag_node_id": "node",
                    "invocation_id": "invoke",
                }
            },
        )
    assert response.status_code == 200
    assert str(Path(tmp_path) / "job/node/invoke/job") in response.text
