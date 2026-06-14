# `discover_nodes` probes LAN-scan candidates strictly sequentially (not with `asyncio.gather`), turning `POST /vampire/v1/discover` into a multi-minute hang and a self-inflicted slowloris; a malformed subnet additionally crashes it with a bare 500

- **Severity:** High — the project's headline "zero-config LAN discovery" endpoint becomes unusable the moment it is actually used for its stated purpose (a `lan_scan` over a real subnet): a single `/24` scan serializes up to 256 connect-timeouts back-to-back, so the request blocks for **~6.4 minutes per port** before returning, far past any client/proxy timeout. The same handler raises an unhandled `ValueError → 500` on a typo'd CIDR. Not Critical only because `lan_scan` is opt-in (default method is `static`) and the endpoint is currently unauthenticated-but-loopback-bound.
- **Category:** performance (event-loop serialization / latency) — with a co-equal error-handling dimension (unvalidated input → bare 500) and a code-consistency contract violation against the sibling refresh path.

- **Summary:** `cluster.discover_nodes` iterates every candidate URL and `await`s `refresh_node(...)` **one at a time inside a `for` loop** (`cluster.py:269-283`). Each probe of an unreachable host blocks for the full connect timeout (default 1500 ms) before the next begins, so an N-host × M-port scan takes ≈ N·M·1.5 s wall-clock serially. The sibling helper `refresh_registered_nodes` already establishes the correct pattern — it fans the identical `refresh_node` calls out concurrently with `asyncio.gather` (`cluster.py:191-193`) — so discovery is the lone path that violates that contract. Separately, `_candidate_urls` calls `ipaddress.ip_network(subnet, strict=False)` (`cluster.py:259`) with no `try/except`, so any malformed `subnets` entry escapes as an uncaught `ValueError` and FastAPI returns an opaque `500 Internal Server Error`.

- **Location:**
  - `src/vampire/cluster.py:269-283` — `discover_nodes`, the sequential `for ... await refresh_node` loop.
  - `src/vampire/cluster.py:186-193` — `refresh_registered_nodes`, the concurrent `asyncio.gather` pattern that discovery fails to follow.
  - `src/vampire/cluster.py:257-264` — the `lan_scan` expansion that emits up to 256 hosts × `len(ports)` candidate URLs.
  - `src/vampire/cluster.py:147-151` — `refresh_node`, where the per-probe timeout (`(timeout_ms or 1500)/1000`) is applied to **all** httpx phases including connect, so each dead host costs the full 1.5 s.
  - `src/vampire/cluster.py:259` — `ipaddress.ip_network(subnet, strict=False)` with no error handling.
  - `src/vampire/api/control.py:89-93` — the `discover` handler that awaits `discover_nodes` directly with no timeout or error envelope.

- **Evidence:**

  The serial loop (the defect):

  ```python
  # src/vampire/cluster.py:269-283
  async def discover_nodes(request: DiscoveryRequest) -> list[Node]:
      """Perform Phase 2 static/dev-subnet discovery and register online nodes."""
      discovered: list[Node] = []
      for base_url in _candidate_urls(request):              # up to 256 * len(ports) URLs
          current = registry.get(_node_id_for_url(base_url))
          node = current or Node(
              id=_node_id_for_url(base_url),
              host=urlparse(base_url).hostname,
              lmstudio_base_url=base_url,
              trusted=not request.trusted_only,
          )
          refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)  # blocks per host
          if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
              discovered.append(refreshed)
      return discovered
  ```

  The sibling that does it correctly (the honored contract):

  ```python
  # src/vampire/cluster.py:186-193
  async def refresh_registered_nodes(*, timeout_ms: int | None = None) -> list[Node]:
      """Refresh every registered node and return the updated snapshot."""
      nodes = registry.list()
      if not nodes:
          return []
      return list(
          await asyncio.gather(*(refresh_node(node, timeout_ms=timeout_ms) for node in nodes))
      )
  ```

  The candidate explosion and the unguarded CIDR parse:

  ```python
  # src/vampire/cluster.py:257-264
  if "lan_scan" in methods:
      for subnet in request.subnets:
          network = ipaddress.ip_network(subnet, strict=False)   # ValueError on bad input -> 500
          for index, host in enumerate(network.hosts()):
              if index >= 256:
                  break
              for port in request.ports:
                  urls.append(f"http://{host}:{port}")
  ```

  The per-host cost, set in `refresh_node`:

  ```python
  # src/vampire/cluster.py:149
  timeout = httpx.Timeout((timeout_ms or 1500) / 1000)   # applies to connect as well as read
  ```

  **Step-by-step manifestation (performance):**
  1. An operator follows the project's own LAN-sharing story and calls `POST /vampire/v1/discover` with `{"methods":["lan_scan"],"subnets":["192.168.1.0/24"],"ports":[1234]}`.
  2. `_candidate_urls` expands this to ~254 host URLs (capped at 256), all on port 1234.
  3. `discover_nodes` enters the `for` loop and `await`s `refresh_node` for the **first** host. In a typical home/office subnet, the overwhelming majority of those addresses have nothing listening on 1234, so each `httpx.AsyncClient.get` hits the **connect timeout of 1.5 s** (an unreachable/filtered host yields no RST; the connect simply times out).
  4. Because the loop `await`s each probe before starting the next, total wall-clock ≈ 254 × 1.5 s ≈ **381 s** for one port; with two ports it doubles to ~12.7 min. The `asyncio` event loop is not blocked (the awaits yield), but the **single request** cannot make progress in parallel, so the HTTP client and any reverse proxy in front (uvicorn/nginx default ~60 s) abort the connection long before `discover_nodes` returns — yet the server keeps grinding through all 254 probes to completion, wasting a full minutes-long scan whose result is discarded. Issue the call a few times and you have a self-inflicted resource pileup (a slowloris against your own gateway).
  5. With `asyncio.gather`, the identical 254 probes overlap and the whole scan finishes in ≈ the single longest probe (~1.5 s) rather than their sum.

  **Step-by-step manifestation (500 on bad subnet):**
  1. Operator sends `{"methods":["lan_scan"],"subnets":["192.168.1.0/24 "]}` (trailing space, or `"192.168.1/24"`, or `"hostname"`).
  2. `ipaddress.ip_network("192.168.1.0/24 ", strict=False)` raises `ValueError: '192.168.1.0/24 ' does not appear to be an IPv4 or IPv6 network`.
  3. Nothing catches it; FastAPI converts the uncaught exception into `500 Internal Server Error` with no OpenAI-style `{"error": ...}` envelope and no indication of which field was wrong — violating the project's own §23 error-format contract that `proxy.py:_upstream_error` honors elsewhere.

- **Impact:** Concrete operator-observable consequences:
  - The advertised LAN-scan discovery effectively **times out from the client's perspective every time** on any real subnet; users will conclude discovery is broken. The server continues a pointless multi-minute scan after the client has given up, so retries stack server-side work.
  - Blast radius is the whole `/vampire/v1/discover` endpoint and, indirectly, the dashboard "Run discovery" button (`tests/test_phase4.py:159`) which calls the same path — a UI click appears to hang.
  - A single typo in the `subnets` field returns a bare, uninformative 500, indistinguishable from a server bug.
  - Triggers whenever `methods` includes `lan_scan` with a non-trivial subnet, which is precisely the documented "discover nodes on my network" use-case.

- **Fix:** Fan the probes out concurrently (mirroring `refresh_registered_nodes`), bound the concurrency with a semaphore so a `/24`-plus scan doesn't open hundreds of sockets at once, and validate subnets up front so a bad CIDR yields a clean 400 instead of a 500. Preserve the invariant that discovery still registers online nodes (via `refresh_node`'s `registry.add`) and returns only online, trust-eligible nodes.

  Before:

  ```python
  # cluster.py
  async def discover_nodes(request: DiscoveryRequest) -> list[Node]:
      discovered: list[Node] = []
      for base_url in _candidate_urls(request):
          current = registry.get(_node_id_for_url(base_url))
          node = current or Node(
              id=_node_id_for_url(base_url),
              host=urlparse(base_url).hostname,
              lmstudio_base_url=base_url,
              trusted=not request.trusted_only,
          )
          refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
          if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
              discovered.append(refreshed)
      return discovered
  ```

  After:

  ```python
  # cluster.py
  _DISCOVERY_MAX_CONCURRENCY = 64

  class DiscoveryInputError(ValueError):
      """Raised when a discovery request contains an unparseable subnet/CIDR."""

  async def discover_nodes(request: DiscoveryRequest) -> list[Node]:
      """Perform Phase 2 static/dev-subnet discovery, probing candidates concurrently."""
      semaphore = asyncio.Semaphore(_DISCOVERY_MAX_CONCURRENCY)

      async def probe(base_url: str) -> Node:
          current = registry.get(_node_id_for_url(base_url))
          node = current or Node(
              id=_node_id_for_url(base_url),
              host=urlparse(base_url).hostname,
              lmstudio_base_url=base_url,
              trusted=not request.trusted_only,
          )
          async with semaphore:
              return await refresh_node(node, timeout_ms=request.timeout_ms)

      candidates = _candidate_urls(request)   # raises DiscoveryInputError on bad subnet (below)
      refreshed = await asyncio.gather(*(probe(url) for url in candidates))
      return [
          node
          for node in refreshed
          if node.status == "online" and (node.trusted or not request.trusted_only)
      ]
  ```

  Guard the CIDR parse in `_candidate_urls`:

  ```python
  # cluster.py:257-264  (inside _candidate_urls)
  if "lan_scan" in methods:
      for subnet in request.subnets:
          try:
              network = ipaddress.ip_network(subnet, strict=False)
          except ValueError as exc:
              raise DiscoveryInputError(f"invalid subnet {subnet!r}: {exc}") from exc
          for index, host in enumerate(network.hosts()):
              if index >= 256:
                  break
              for port in request.ports:
                  urls.append(f"http://{host}:{port}")
  ```

  Translate the input error to a 400 at the boundary:

  ```python
  # api/control.py:89-93
  @router.post("/discover")
  async def discover(request: DiscoveryRequest | None = None) -> dict[str, Any]:
      try:
          nodes = await discover_nodes(request or DiscoveryRequest())
      except DiscoveryInputError as exc:
          raise HTTPException(status_code=400, detail=str(exc)) from exc
      return {"object": "vampire.discovery_result", "nodes": [n.model_dump() for n in nodes]}
  ```

  Notes:
  - No `# type: ignore` to remove here, but this fix should be cross-referenced with the already-logged per-request-httpx-client suggestion (`2026-06-14_0612`): once `refresh_node` shares a pooled client, the concurrent fan-out below benefits even more (one connection pool instead of 254 throwaway clients). The two fixes compose cleanly.
  - Concurrency note: `refresh_node` ends with `registry.add(updated)`; concurrent `registry.add` calls on CPython's dict are safe between awaits, but be aware of the separately-logged `refresh_node`-resurrects-deleted-nodes race (`2026-06-14_0602`) — the gather here increases the number of in-flight `refresh_node` bodies, so fixing that race is a sensible companion change.
  - Docs to update: if `docs/`/`DESIGN-API.md §12` claims discovery is "fast"/"parallel", this brings code in line; if it documents a synchronous bounded scan, note the new `_DISCOVERY_MAX_CONCURRENCY` cap and the 400 error class.

- **Test:** A regression test that fails today (the serial loop makes it slow / the bad-subnet path 500s) and passes after the fix. The timing assertion uses a slow fake `refresh_node` to prove probes overlap.

  ```python
  # tests/test_phase2.py
  import asyncio
  import time
  import pytest
  from vampire import cluster
  from vampire.models import DiscoveryRequest, Node

  @pytest.mark.anyio  # or asyncio, per the suite's config
  async def test_lan_scan_probes_run_concurrently(monkeypatch):
      """254 hosts each costing 0.1s must finish well under the serial sum (~25s)."""
      async def slow_refresh(node: Node, *, timeout_ms=None) -> Node:
          await asyncio.sleep(0.1)               # simulate a connect timeout per host
          return node.model_copy(update={"status": "offline"})
      monkeypatch.setattr(cluster, "refresh_node", slow_refresh)

      started = time.perf_counter()
      await cluster.discover_nodes(
          DiscoveryRequest(methods=["lan_scan"], subnets=["192.168.1.0/24"], ports=[1234])
      )
      elapsed = time.perf_counter() - started

      # Serial today: ~254 * 0.1s = ~25s. Concurrent (cap 64): a handful of 0.1s waves < 1s.
      assert elapsed < 2.0, f"discovery serialized probes: took {elapsed:.1f}s"

  def test_discover_rejects_malformed_subnet(client):
      """A bad CIDR must yield a clean 400, not a bare 500."""
      resp = client.post(
          "/vampire/v1/discover",
          json={"methods": ["lan_scan"], "subnets": ["not-a-cidr"]},
      )
      assert resp.status_code == 400
      assert "invalid subnet" in resp.json()["detail"]
  ```

  Today the first test takes ~25 s and fails the `< 2.0` assertion (proving serialization); the second returns 500 and fails the `== 400` assertion (proving the unguarded parse). After the fix both pass.

- **Effort & risk:** ~30–40 lines changed across two files (`cluster.py`, `api/control.py`), plus ~25 lines of new tests. Backward-compatible: the endpoint's request/response shape is unchanged; the only observable differences are (a) `lan_scan` returns dramatically faster, (b) a previously-500-ing malformed subnet now returns a structured 400. The semaphore cap (`_DISCOVERY_MAX_CONCURRENCY = 64`) is a conservative default that bounds simultaneous sockets; tune via constant if needed. Low risk — the concurrent pattern is already proven in `refresh_registered_nodes`, and `registry.add` ordering for genuinely-distinct node ids is independent so the gather introduces no new key collisions for the LAN-scan case.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~221,644 tok · output ~10,013 tok (summed from this session's logged `in=`/`out=` across 8 API calls) · est. cost ~$4.07 (input 221644/1e6·$15 = $3.32 + output 10013/1e6·$75 = $0.75) · run started 16:32 finished 16:35 UTC. Estimated — final output tokens are emitted after logging.
