## 0.1.0

* **This package now owns the `/invoke` transport for the reserved fields.**
  `unstructured_platform_plugins.invocation_settings` holds the `/invoke` binding dependency and
  body cap, the `/metadata` capability route, the request-scoped accessors, and `http_status_for`
  — the HTTP spelling of the
  library's normative `blame` → status rule. It sits on `utic-invocation-settings >=0.4.0`,
  which owns the *settings contract* — which key carries settings, how a sealed envelope is told
  from plaintext, and what an absent field is allowed to mean. That split is deliberate: the
  absence rule is a security decision and belongs next to the crypto it governs, while request
  handling and route registration belong here, where a web framework is already a dependency.
  Nothing about the sealed-settings wire format is decided in this repository.
* **This package now owns the `invocation_context` identity model.**
  `unstructured_platform_plugins.invocation_context` holds `InvocationContext`,
  `extract_context`, `dimensions`, `RESERVED_CONTEXT_KEY`, `DIMENSION_FIELDS`,
  `SUPPORTED_CONTEXT_VERSIONS` and `UnsupportedContextVersionError`. The context is `/invoke`
  protocol identity — no crypto, no secrets — so it lives with the plugin protocol. Its errors
  subclass the shared `InvocationSettingsError` taxonomy, so hosts classify context failures with
  the same `reason`/`blame` machinery as settings failures. This module is the public home for
  the surface `utic-invocation-settings 0.2.x` carried and its `0.3.0` removed.
* **Every wrapped app installs it at construction.** The reserved `invocation_settings` /
  `invocation_context` fields are handled outside the generated handler schema, a sealed
  `dag_node_settings` member is opened with this pod's mounted workload key, and the resolved
  values are exposed through `current_invocation_settings()` / `current_invocation_context()`.
  An absent field preserves the existing fallback behaviour; under
  `FF_REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS` missing or plaintext settings fail closed.
  Repeated installation is safe: the dependency installs once and the last `/metadata`
  registration wins.
* **Extraction is a route dependency.** `bind_invocation_envelope` reads the body the framework
  buffered and parsed (`request.json()` is Starlette-cached), so the `/invoke` body is held and
  decoded exactly once per request. `install_invocation_envelope` contributes that path-aware
  dependency through the router's public dependency list before `/invoke` is registered; no
  private FastAPI dependency graph is mutated. It also registers the failure response shape and
  installs `InvokeBodyLimitMiddleware`, a streaming byte counter that answers 413 over the cap
  without buffering. Async-generator plugins explicitly re-enter the captured request binding
  inside response iteration, so streaming stays correct independently of FastAPI's yield-dependency
  cleanup timing.
* **Sealed settings consumption remains opt-in.** Pass
  `invoke_with_sealed_dag_node_settings=True` to `wrap_in_fastapi` / `generate_fast_api` (or
  `--sealed-dag-node-settings` on the CLI) only for a plugin that consumes per-invoke settings;
  it advertises that the application accepts and acts on sealed `dag_node_settings`. Transport
  support alone continues to advertise only `invocation_settings` and `invocation_context`. A
  plugin that serves a custom `/metadata` payload must register it via `add_metadata_route` (which
  replaces the wrapper's route) — a plain `@app.get("/metadata")` added after construction is
  shadowed by the wrapper's earlier registration.
* **Resolution runs off the event loop.** A cold resolve is an RSA unwrap of a couple of
  milliseconds and this dependency fronts every invoke on the pod, so it is dispatched with
  `asyncio.to_thread` rather than blocking the loop.
* **Failures map through the library's blame taxonomy**, not a flat 500: only a caller-fixable
  fault answers 422. Sealing drift, an envelope addressed to another recipient and a broken local
  mount are all 5xx, which keeps the controller's blame classification off the customer. Responses
  carry the error's class name and never its message, which can embed request-controlled values.
* **Sync plugin functions now observe request-scoped context.** `invoke_func` copies the current
  context into the executor thread; previously `run_in_executor` dropped contextvars, so a sync
  function reading a request-scoped binding (such as `current_invocation_settings()`) would see
  it as absent and could take an unintended fallback path.
* **Python floor is now 3.11** (required by `utic-invocation-settings`).

## 0.0.45

* **`/invoke` no longer demands a body from a plugin whose parameters are all optional.** A pydantic
  body parameter with no default is mandatory even when every field inside the model is optional, so
  such a plugin required a body that no caller has a reason to populate — and before it grew those
  parameters the same plugin accepted no body at all, which made adding one look
  backward-compatible while silently flipping the HTTP contract to 422 for every bodyless caller.
  An absent body now resolves each field to its own default, which is what the signature already
  promised. Plugins with at least one required field are unchanged: a missing `file_data` still
  fails validation rather than arriving as `None`.
* **An optional `file_data` no longer 500s when absent.** The wrapper converted `file_data` from its
  dict form unconditionally, so a plugin declaring it optional hit
  `AttributeError: 'NoneType' object has no attribute 'model_dump'` on any body that omitted it —
  previously reachable via `POST {}`, and via a bodyless request once the change above landed. `None`
  is now passed through untouched and only a real value is converted.

## 0.0.44

* **Ignore SIGTERM in plugin uvicorn Servers**: plugin webservers now keep
  serving on SIGTERM so their controller container can finish dispatching
  in-flight work before the pod is SIGKILLed. SIGINT still terminates for
  local-dev Ctrl-C.

## 0.0.43

* **Deprecate `wrap_in_fastapi`** - Mark `wrap_in_fastapi` (and the `etl-uvicorn` CLI it backs) as deprecated via PEP 702 `@deprecated`. New plugins should build a FastAPI app directly with explicit handlers for the plugin contract routes.

## 0.0.42

* **Support "none" value for OTEL_TRACES_EXPORTER and OTEL_METRICS_EXPORTER** - Filter "none" from exporter lists and return None when no exporters configured to properly disable OpenTelemetry instrumentation

## 0.0.39

* **Remove wrap_error logic as exceptions are categorized in unstructured-ingest**

## 0.0.29

* **Support persisting file data changes**

## 0.0.28

* **Isolate what gets bundled in package**

## 0.0.27

* **Update repo to us `uv`**

## 0.0.26

* **Bump `unstructured-ingest` to 0.5.23**
* **Change how we import FileData type for slimmer import graph at runtime**

## 0.0.25

* **Remove message channels from input signature**

## 0.0.24

* **Add support for passing messages back other than errors**

## 0.0.23

* **Handle errors in streaming responses**

## 0.0.22

* **Bump `unstructured-ingest` to 0.4.0**

## 0.0.21

* **Bump `unstructured-ingest` to 0.3.15**

## 0.0.20

* **Expand support to Python 3.13**

## 0.0.19

* **Add more granular error response texts and codes**

## 0.0.18

* **Receive ingest 0.3.12**

## 0.0.17

* **Bugfix supporting list union types in response**

## 0.0.16

* **Bugfix for file data deserialization**

## 0.0.15

* **Bugfix for file data serialization**

## 0.0.14

* **Add support for batch file data**

## 0.0.13

* **Conform to PEP-625 compliance for project naming**

## 0.0.12

* **Bugfix: Fix UnrecoverableException exception handling to include full response**

## 0.0.11

* **Bugfix: Add UnrecoverableException exception handling back**

## 0.0.10

* **Bugfix: Add `None` support in mapping `FileDataMeta` response**

## 0.0.9

* **Support optionally exposing addition metadata around FileData**

## 0.0.8

* **reduce usage data log level** We do not want to have so much verbosity for something that might happen a lot
* **Support unrecoverable errors** Throw a 512 error for an unrecoverable error

## 0.0.7

* **Improve code separation to help with unit tests**

## 0.0.6

* **Support streaming response types for /invoke if callable is async generator**

## 0.0.5

* **Improve logging to hide body in case of sensitive data unless TRACE level**

## 0.0.4

### Fixes

* **Do not block event loop when running plugin code**

## 0.0.3

### Features

* **OTEL middleware added**

## 0.0.2

### Enhancements

### Features

### Fixes

* **FileData Literal not handled** FileData content was updated to use Literal rather than Enum. This case needed to be added. 

## 0.0.1

### Enhancements

### Features

### Fixes

* **Model generation when schema is empty fixed** Key error was being thrown when properties not in schema, but this doesn't exist when schema is null. Null check added. 

## 0.0.0

### Enhancements

### Features

* **Initial Release** First release of the project with all existing implementations in place. 

### Fixes
