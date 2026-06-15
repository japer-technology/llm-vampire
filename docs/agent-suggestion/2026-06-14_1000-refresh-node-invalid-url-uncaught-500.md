# `refresh_node` lets `httpx.InvalidURL` escape its `except` clause — one malformed node URL 500s every cluster endpoint

- **Severity:** High — a single malformed `lmstudio_base_url` (operator typo or attacker-supplied during `POST /vampire/v1/nodes`) turns registration, `/v1/models`, `/vampire/v1/models`, and routed `/v1/chat/completions` into uncaught `500 Internal Server Error`s, and the bad node is persisted so the failure is *sticky* across the whole gateway.
- **Category:** error-handling (with an api-correctness / type-safety dimension).

## Summary
`refresh_node` interrogates a node's `/v1/models` and is documented/coded to convert *all* failures into an `offline` node with `last_error` set. Its `except` clause catches only `(httpx.HTTPError, ValueError)`, but httpx raises `httpx.InvalidURL` for a malformed URL (bad port, control chars, IDNA failure) and **`httpx.InvalidURL` is not a subclass of `httpx.HTTPError` *or* `ValueError`**. The exception escapes, FastAPI returns a bare `500 Internal Server Error`, the bad node stays registered, and every subsequent cluster-wide refresh re-raises — poisoning `/v1/models`, `/vampire/v1/models`, and the routing fast-path for *all* models, not just the broken node.

## Location
- `src/vampire/cluster.py:157-200` — `refresh_node`, specifically the `except (httpx.HTTPError, ValueError) as exc:` on **line 182** and the failing call on **line 169**.
- Blast-radius callers that fan this out cluster-wide:
  - `src/vampire/cluster.py:203-218` — `refresh_registered_nodes` (`asyncio.gather` — one bad node fails the whole gather).
  - `src/vampire/api/openai_compat.py:39` — `list_models` → `refresh_registered_nodes`.
  - `src/vampire/api/control.py:69,90,119` — `register_node`, `patch_node`, `list_vampire_models`.

## Evidence

### The narrow `except` clause
`src/vampire/cluster.py:164-200`:
```python
    timeout = httpx.Timeout((timeout_ms or 1500) / 1000)
    base_url = node.lmstudio_base_url.rstrip("/")
    http_client = client or proxy.build_async_client()
    started = perf_counter()
    try:
        response = await http_client.get(f"{base_url}/v1/models", timeout=timeout)  # line 169
        latency_ms = round((perf_counter() - started) * 1000, 3)
        response.raise_for_status()
        updated = node.model_copy(update={ ... "status": "online", ... })
    except (httpx.HTTPError, ValueError) as exc:        # line 182  <-- does NOT catch InvalidURL
        latency_ms = round((perf_counter() - started) * 1000, 3)
        updated = node.model_copy(update={ ... "status": "offline", ... "last_error": str(exc)})
    finally:
        if client is None:
            await http_client.aclose()
```

### `httpx.InvalidURL` is outside the caught hierarchy
The contract this code intends to honor is *"any reachability/parse failure becomes an offline node"* — see the sibling handling in `proxy.proxy_request_with_body` (`src/vampire/proxy.py:150`) which catches `httpx.RequestError` and the `_coerce_model_cards`/`ValueError` path for bad JSON. But the httpx class hierarchy (verified against the repo's pinned `httpx 0.28.1`) is:

```
InvalidURL          -> (InvalidURL, Exception)                 # NOT a RequestError, NOT an HTTPError
UnsupportedProtocol -> (..., RequestError, HTTPError, ...)
ConnectError        -> (..., NetworkError, RequestError, HTTPError, ...)
```

```
$ python -c 'import httpx; print(issubclass(httpx.InvalidURL, httpx.HTTPError), issubclass(httpx.InvalidURL, ValueError))'
False False
```

`build_request` (called inside `http_client.get`) raises `InvalidURL` *before any I/O* for several inputs that survive Pydantic's `str`-typed `lmstudio_base_url` field (no URL validation exists on `Node.lmstudio_base_url`, `models.py:78`):

```
control char in path     -> InvalidURL   HTTPError:False RequestError:False ValueError:False
non-ascii host idna fail -> InvalidURL   HTTPError:False RequestError:False ValueError:False
bad port (':notaport')   -> InvalidURL   HTTPError:False RequestError:False ValueError:False
userinfo control char    -> InvalidURL   HTTPError:False RequestError:False ValueError:False
```

### End-to-end reproduction against the real app
Registering a node whose URL has a non-numeric port (a plausible typo: `http://node:notaport`, or `http://node:1234x`) reproduces the cascade. Captured traceback from `cluster.refresh_node`:

```
  File ".../src/vampire/cluster.py", line 169, in refresh_node
    response = await http_client.get(f"{base_url}/v1/models", timeout=timeout)
  ...
  File ".../httpx/_urlparse.py", line 411, in normalize_port
    raise InvalidURL(f"Invalid port: {port!r}")
httpx.InvalidURL: Invalid port: 'notaport'
```

Driving it through `TestClient(create_app())`:

```
POST /vampire/v1/nodes  -> 500   body: Internal Server Error
registry now has: ['bad']                  # <-- node persisted by register_node BEFORE refresh
GET /v1/models          -> 500   body: Internal Server Error
GET /vampire/v1/models  -> 500
```

**Step-by-step manifestation:**
1. Operator (or any caller able to reach the control API — note auth is opt-in, `auth_token` defaults to `""`) `POST /vampire/v1/nodes` with `{"id":"bad","lmstudio_base_url":"http://node:notaport"}`.
2. `register_node` (`control.py:68`) calls `registry.add(node)` **first**, persisting the node, then `await refresh_node(...)`.
3. `refresh_node` line 169 calls `http_client.get` → httpx `build_request` → `normalize_port` raises `InvalidURL`.
4. The `except (httpx.HTTPError, ValueError)` on line 182 does **not** match `InvalidURL`; the `finally` closes the client and the exception propagates.
5. FastAPI has no handler for `httpx.InvalidURL` → bare `500 Internal Server Error` (not even the OpenAI error envelope from `proxy._upstream_error` / `auth_exception_handler`).
6. The bad node is now permanently in the registry. Every later `GET /v1/models` (`openai_compat.py:39`) and `GET /vampire/v1/models` (`control.py:119`) calls `refresh_registered_nodes`, whose `asyncio.gather` (`cluster.py:212-217`) re-raises the same `InvalidURL` — so the *entire* model catalogue and any routed completion that triggers a refresh now 500s for **every** model, until someone manually `DELETE`s the poisoned node.

## Impact
- **Observable:** clients get `500 Internal Server Error` with a plain-text body (violates DESIGN-API.md §23 OpenAI error-envelope contract, which the rest of the codebase honors via `_upstream_error` and `auth_exception_handler`).
- **Blast radius:** not confined to the one bad node. Because `refresh_registered_nodes` uses `asyncio.gather` with default `return_exceptions=False`, one malformed node fails the *whole* refresh, knocking out `/v1/models`, `/vampire/v1/models`, and the routing path's `list_models` for all callers.
- **Stickiness / DoS:** `register_node` persists the node before the failing refresh, so the 500 is durable across requests and process-wide. A single bad registration is an availability incident requiring manual `DELETE /vampire/v1/nodes/{id}` to clear — and listing nodes to find it still works, but model endpoints stay down meanwhile.
- **Trigger surface:** any operator typo in a base URL (`:1234x`, trailing whitespace that becomes a control char, an internationalized hostname that fails IDNA), or any party able to POST to the control API when auth is unset (the default).

## Fix
Broaden the `except` to also catch `httpx.InvalidURL` (and, defensively, `httpx.StreamError`/`httpx.CookieConflict` — but `InvalidURL` is the real bug). Treat a malformed URL exactly like an unreachable node: mark it `offline` with `last_error`. Additionally harden the cluster fan-out so one bad node can never fail the whole gather.

### Before (`cluster.py:182`)
```python
    except (httpx.HTTPError, ValueError) as exc:
```

### After
```python
    # httpx.InvalidURL is NOT a subclass of HTTPError/RequestError, so a malformed
    # lmstudio_base_url (bad port, control chars, IDNA failure) would otherwise
    # escape and 500 every cluster endpoint. Treat it as an offline node, matching
    # the "all probe failures become offline" contract documented in this function.
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
```

`httpx.HTTPError` already covers `RequestError`/`HTTPStatusError`; adding `httpx.InvalidURL` (a top-level `Exception` subclass) closes the gap. `ValueError` is retained for `response.json()` decode failures via `_coerce_model_cards`.

### Defense-in-depth: isolate one bad node in the fan-out (`cluster.py:203-218`)
Make `refresh_registered_nodes` resilient so a future un-anticipated exception in one node can't blank the whole catalogue:

```python
async def refresh_registered_nodes(
    *, timeout_ms: int | None = None, client: httpx.AsyncClient | None = None
) -> list[Node]:
    """Refresh every registered node and return the updated snapshot."""
    nodes = registry.list()
    if not nodes:
        return []
    results = await asyncio.gather(
        *(
            refresh_node(node, timeout_ms=timeout_ms, client=client)
            if client is not None
            else refresh_node(node, timeout_ms=timeout_ms)
            for node in nodes
        ),
        return_exceptions=True,
    )
    refreshed: list[Node] = []
    for node, result in zip(nodes, results):
        if isinstance(result, Node):
            refreshed.append(result)
        else:  # pragma: no cover - belt-and-suspenders; refresh_node already swallows probe errors
            logger.warning("refresh of node %s failed: %r", node.id, result)
            refreshed.append(node)
    return refreshed
```
(That requires adding `import logging` / `logger = logging.getLogger(__name__)` to `cluster.py`.)

### Optional, recommended: validate the URL at the API boundary
Reject malformed URLs at `POST /vampire/v1/nodes` so they never persist. Change `Node.lmstudio_base_url` (`models.py:78`) from `str` to a validated form, e.g. a `field_validator` that runs `httpx.URL(value)` and requires `scheme in {"http","https"}` and a host — raising a 422 instead of letting the bad value reach `refresh_node`. This dovetails with the still-open SSRF suggestion (`2026-06-14_0828-ssrf-...`) and the same validator can enforce both. Keep the `refresh_node` catch regardless, as defense in depth.

**Invariant to preserve:** `refresh_node` must never raise to its callers for a *probe-time* failure; it always returns a `Node` (online or offline). The blast-radius fix preserves the existing "registered-then-refreshed" semantics and the offline `last_error` behavior asserted by `test_discover_does_not_register_offline_candidates`.

No `# type: ignore` to remove here. No docs need changing beyond optionally noting URL validation in DESIGN-API.md §13.

- **APPLIED 2026-06-15:** Set to Taken and implemented by treating `httpx.InvalidURL` as an offline probe failure, isolating unexpected per-node refresh failures during fan-out, and adding malformed URL regression coverage.

## Test
A regression test that fails today (uncaught `InvalidURL` → 500) and passes after the fix. Add to `tests/test_phase2.py`:

```python
def test_refresh_node_handles_malformed_url_as_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed lmstudio_base_url must yield an OFFLINE node, never a 500.

    httpx raises httpx.InvalidURL (not an HTTPError/ValueError) for a bad port,
    so the probe must still be funneled into the offline path.
    """
    from vampire.registry import registry as node_registry

    node_registry.clear()
    node = Node(id="bad", lmstudio_base_url="http://node:notaport")

    # No transport needed: httpx raises InvalidURL inside build_request, before I/O.
    refreshed = asyncio.run(cluster.refresh_node(node))

    assert refreshed.status == "offline"
    assert refreshed.last_error is not None
    assert "port" in refreshed.last_error.lower() or "url" in refreshed.last_error.lower()


def test_models_endpoints_survive_one_malformed_node(client: TestClient) -> None:
    """One poisoned node must not 500 the whole cluster model catalogue."""
    from vampire.registry import registry as node_registry

    node_registry.clear()
    # A healthy node (probed against the in-process mock cluster) ...
    client.post(
        "/vampire/v1/nodes",
        json={"id": "good", "lmstudio_base_url": "http://good:1234"},
    )
    # ... and a node whose URL httpx cannot parse.
    bad = client.post(
        "/vampire/v1/nodes",
        json={"id": "bad", "lmstudio_base_url": "http://node:notaport"},
    )
    assert bad.status_code == 200          # offline registration, NOT 500
    assert bad.json()["status"] == "registered"

    resp = client.get("/v1/models")
    assert resp.status_code == 200         # fails today with 500
    ids = {m["id"] for m in resp.json()["data"]}
    assert "good-model" in ids             # healthy node still surfaces
```

Today, `test_refresh_node_handles_malformed_url_as_offline` raises `httpx.InvalidURL` out of `asyncio.run`, and `test_models_endpoints_survive_one_malformed_node` asserts `200` but gets `500`. After the fix both pass.

## Effort & risk
- **Lines changed:** ~1 line for the core fix (the `except` tuple); ~12 lines for the `refresh_registered_nodes` hardening + `logging` import; ~6 lines if the optional `field_validator` is added.
- **Files touched:** `src/vampire/cluster.py` (required); optionally `src/vampire/models.py`; plus `tests/test_phase2.py`.
- **Backward-compat:** fully compatible. Malformed nodes previously caused a 500; they now register as `offline` with `last_error` — strictly better behavior, consistent with unreachable-node handling. The `return_exceptions=True` change keeps the return type `list[Node]` and only changes the failure mode from "raise" to "log + keep prior snapshot," which no current test depends on. The optional 422-on-bad-URL validator is a *stricter* input contract; verify no existing test registers an intentionally weird-but-parseable URL (current tests all use well-formed `http://host:port` URLs, so this is safe).

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~1,326,415 tok · output ~12,097 tok · est. cost ~$20.80 · run started 20:00 finished 20:05.
