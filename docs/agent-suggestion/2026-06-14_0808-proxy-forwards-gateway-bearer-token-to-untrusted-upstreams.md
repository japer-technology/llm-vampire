# The transparent proxy forwards the client's `Authorization` header — i.e. the gateway's own secret `VAMPIRE_AUTH_TOKEN` — verbatim to every downstream LM Studio node, leaking the privileged control-plane credential to untrusted LAN backends

- **Severity:** High — once an operator sets `VAMPIRE_AUTH_TOKEN` (the project's own, recently-added, documented way to lock the gateway down), that exact secret is silently exfiltrated on the wire to every upstream the gateway proxies to, including untrusted nodes the gateway itself discovered on the LAN. A single malicious or compromised backend harvests the bearer token and then has full, authenticated access to the privileged `/vampire/v1/*` control plane (register/delete nodes, change routing, flip share mode). Not rated Critical only because it requires the operator to (a) enable auth and (b) route to at least one attacker-controlled or eavesdroppable upstream — but both are explicitly supported, first-class configurations of this project.
- **Category:** security (credential egress / token leakage) — with a secondary code-vs-doc drift dimension (the proxy's own header-filtering docstring claims it only forwards "end-to-end request headers safe to forward upstream").

## Summary

`proxy_request_with_body` forwards the inbound request headers to the downstream LM Studio node after stripping only hop-by-hop headers plus `host`/`content-length` (`_DROP_REQUEST_HEADERS`). `Authorization` is **not** in that drop set, so it is forwarded verbatim. When the gateway is locked down with `VAMPIRE_AUTH_TOKEN`, clients authenticate by sending `Authorization: Bearer <gateway-token>` — and that same privileged token is then relayed to whatever upstream the request lands on. Because the routing/discovery layer can point requests at nodes the gateway discovered on the LAN (and at nodes the operator merely registered but does not control), the gateway leaks its own admin credential to backends that have no business seeing it.

## Location

- `src/vampire/proxy.py:32-44` — the header drop set that omits `authorization`.
- `src/vampire/proxy.py:68-76` — `_filter_request_headers`, whose docstring claims it returns only headers "safe to forward upstream".
- `src/vampire/proxy.py:133` — where the (unfiltered-for-auth) headers are built for the upstream request.
- Credential definition / enforcement that makes the leaked value sensitive:
  - `src/vampire/config.py:38` — `auth_token: str = ""`.
  - `src/vampire/auth.py:32-43` — `require_auth` accepts the token via the inbound `Authorization: Bearer` header (so that header *is* the secret).
  - `src/vampire/api/_auth.py:16-25` — the same token gates the privileged `/vampire/v1/*` control plane.
- Leak amplifiers (requests routed to non-loopback / discovered / untrusted nodes):
  - `src/vampire/api/openai_compat.py:154-164` — routed requests proxy to `node.lmstudio_base_url` of a selected node.
  - `src/vampire/cluster.py:301-327` — `discover_nodes` registers LAN-scanned nodes that subsequently become routing targets.

## Evidence

The drop set explicitly enumerates what is removed, and `authorization` is absent:

```python
# src/vampire/proxy.py:32-44
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_DROP_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {"host", "content-length"}
```

The filter forwards everything else, with a docstring that asserts safety it does not actually deliver:

```python
# src/vampire/proxy.py:68-76
def _filter_request_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    """Return end-to-end request headers safe to forward upstream.

    Custom client headers, including future ``X-Vampire-*`` controls, are
    preserved. Only transport-specific headers that httpx must recompute or
    manage itself are removed.
    """
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in _DROP_REQUEST_HEADERS]
```

And those headers are sent verbatim upstream:

```python
# src/vampire/proxy.py:133-142
headers = _filter_request_headers(httpx.Headers(request.headers.raw))

client, should_close_client = _request_client(request)
upstream_request = client.build_request(
    request.method,
    url,
    params=dict(request.query_params),
    headers=headers,
    content=body,
)
```

The forwarded `Authorization` value is precisely the gateway's secret. `require_auth` reads the secret from that header:

```python
# src/vampire/auth.py:38-43
header = request.headers.get("authorization", "")
scheme, _, presented = header.partition(" ")
if scheme.lower() != "bearer" or not presented:
    raise AuthError("Missing bearer token.")
if not hmac.compare_digest(presented, token):
    raise AuthError("Invalid bearer token.")
```

And the *same* `auth_token` gates the privileged control plane (`src/vampire/api/_auth.py:19-25`), so the leaked value is an admin credential, not merely a data-plane key.

### Step-by-step manifestation

1. Operator follows the project's hardening guidance and sets `VAMPIRE_AUTH_TOKEN=s3cret` (config.py:38). Now both `/v1/*` (auth.py) and `/vampire/v1/*` (_auth.py) require `Authorization: Bearer s3cret`.
2. A normal OpenAI client is configured with `api_key="s3cret"` and base URL pointing at the gateway. Every request it makes carries `Authorization: Bearer s3cret`.
3. The request hits `/v1/chat/completions` → `_route_or_proxy` → `proxy_request_with_body`. `_filter_request_headers` strips hop-by-hop + host/content-length but **keeps** `authorization` (proxy.py:75).
4. The upstream request is built (proxy.py:136) and sent (proxy.py:144) to `node.lmstudio_base_url` — which, for routed/discovered traffic, can be any LAN node (openai_compat.py:156; cluster.py:296,316). LM Studio ignores the header, but the bytes have already crossed the wire to that host.
5. The upstream node operator (or anyone able to observe plaintext `http://` traffic to it — discovery only ever forms `http://` URLs, cluster.py:296) reads `Authorization: Bearer s3cret` from the inbound request.
6. The attacker replays `Authorization: Bearer s3cret` against the gateway's `/vampire/v1/nodes`, `/vampire/v1/routes`, `/vampire/v1/share` — all of which pass `require_control_auth` and grant full control-plane access.

The contract violated is the universal reverse-proxy invariant **"do not forward the proxy's own client-facing credentials to the origin"** — the same class of bug as a CDN leaking its edge auth header to origin. The proxy already understands credential-bearing headers are special: it deliberately strips `proxy-authorization` (proxy.py:37). It simply forgot the one that actually carries this gateway's secret.

## Impact

- **What leaks:** the gateway's bearer token — which is simultaneously the data-plane key (`/v1/*`) and the control-plane admin key (`/vampire/v1/*`).
- **Who sees it:** every downstream node the gateway proxies to. With LAN discovery (a headline feature), that set includes hosts the operator never hand-vetted; with `http://` upstreams (the only scheme discovery produces), any on-path observer sees it in cleartext.
- **Blast radius:** full control-plane compromise — an attacker can register a malicious node, delete legitimate nodes, rewrite routing policies to funnel all inference (including prompts/responses) through attacker infrastructure, and toggle share mode. This converts a passive credential leak into active traffic interception.
- **When it triggers:** on the very first authenticated proxied request after `VAMPIRE_AUTH_TOKEN` is set. The failure mode is worst exactly when the operator believes they have *added* security.
- **Detectability:** invisible in the localhost test suite (the mock upstream never inspects/asserts on `Authorization`), so it ships silently.

## Fix

Strip `authorization` (and, defensively, `cookie`) from the headers forwarded upstream. The gateway terminates its own auth; the upstream LM Studio node has an independent trust relationship and should receive only an explicitly-configured upstream credential, never the client's gateway token.

Minimal, targeted change in `src/vampire/proxy.py`:

```python
# BEFORE (proxy.py:44)
_DROP_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {"host", "content-length"}

# AFTER
# The gateway terminates client auth itself; never relay the client's
# gateway-facing credentials to a downstream node (which may be untrusted or
# LAN-discovered). ``cookie`` is dropped for the same credential-egress reason.
_DROP_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {
    "host",
    "content-length",
    "authorization",
    "cookie",
}
```

Update the now-inaccurate docstring so it stops over-promising:

```python
# proxy.py:68-76 (AFTER)
def _filter_request_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    """Return end-to-end request headers safe to forward upstream.

    Custom client headers, including ``X-Vampire-*`` controls, are preserved.
    Transport-specific headers that httpx recomputes are removed, and so are
    the client's gateway-facing credentials (``authorization``/``cookie``):
    the gateway authenticates clients itself and must not leak its own bearer
    token to downstream — possibly untrusted — LM Studio nodes.
    """
    ...
```

**Preserve this invariant going forward:** any future per-node upstream credential must be *injected* by the gateway (e.g. from `Node`-level config), not passed through from the client. If/when upstream auth is added, set it explicitly after the strip, e.g. `headers.append(("authorization", node.upstream_token))`.

**Docs to reconcile:** DESIGN-API.md:1163-1173 / 1405-1407 show `Authorization: Bearer ***` against the gateway; that is correct for the *client→gateway* hop. Add a one-line note that the gateway does **not** propagate this header to upstream nodes, so the spec and code agree.

No `# type: ignore` is involved.

## Test

Add to `tests/test_phase1.py` (the mock upstream there already records request metadata; extend it to capture `authorization`). This test fails today (the header is forwarded) and passes after the strip.

```python
def test_proxy_strips_client_authorization_from_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gateway's own bearer token must never reach a downstream node."""
    seen: dict[str, str | None] = {}

    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        seen["authorization"] = request.headers.get("authorization")
        return JSONResponse(
            {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        )

    original = proxy.build_async_client
    proxy.build_async_client = lambda: httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream)
    )
    try:
        # Lock the gateway down so the client must present the gateway token.
        monkeypatch.setenv("VAMPIRE_AUTH_TOKEN", "s3cret")
        get_settings.cache_clear()  # config.get_settings is lru_cached
        with TestClient(create_app()) as client:
            resp = client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer s3cret"},
                json={"model": "local-model",
                      "messages": [{"role": "user", "content": "hello"}]},
            )
        assert resp.status_code == 200
        # The privileged gateway token must NOT have been relayed upstream.
        assert seen["authorization"] is None
    finally:
        proxy.build_async_client = original
        get_settings.cache_clear()
```

(If `get_settings` is not `lru_cache`-backed in the current tree, drop the `cache_clear()` calls and `monkeypatch.setattr` the settings accessor used by `auth.require_auth`, mirroring `tests/test_auth.py:25`.) The key assertion is `seen["authorization"] is None`: before the fix it equals `"Bearer s3cret"`.

## Effort & risk

- **Lines changed:** ~5 in `proxy.py` (drop-set entries + docstring), ~1 doc note in DESIGN-API.md, ~30 for the regression test.
- **Files touched:** `src/vampire/proxy.py`, `tests/test_phase1.py`, optionally `DESIGN-API.md`.
- **Backward-compat:** Negligible risk. Today LM Studio does not require auth, so nothing relies on the leaked header reaching it. The only behavioral change is that a client-supplied `Authorization`/`Cookie` no longer crosses to upstream — which is exactly the desired security posture. If a deployment genuinely needs upstream auth, that must be configured per-node (and injected by the gateway), not smuggled through the client header; this change makes that boundary explicit.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~unknown tok · output ~3400 tok · est. cost ~$0.26 (output-only estimate; input figure unavailable from logs) · run started 08:08 finished 08:10.
