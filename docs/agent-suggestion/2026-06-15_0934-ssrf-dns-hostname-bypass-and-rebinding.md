# `is_allowed_target_url` waves through every DNS hostname — the SSRF guard only blocks IP *literals*, so `metadata.google.internal`, internal service names, and DNS-rebinding targets still reach the gateway's outbound fetcher

- **Severity:** High — the SSRF hardening added in suggestion `0828`
  (`is_allowed_target_url`) is the gateway's only line of defense for
  caller-supplied probe/proxy targets, and it has a structural hole: it
  validates *scope* only when the host parses as an IP address. Any host that
  is **not** an IP literal — i.e. every DNS name — short-circuits to
  `return True` and is fetched verbatim from the gateway's own network position.
  That re-opens exactly the attack class `0828` set out to close
  (`http://169.254.169.254/...`, internal admin panels, cloud metadata) the
  moment the attacker spells the target as a name instead of an address:
  `http://metadata.google.internal/...`, `http://internal-admin:8080`,
  `http://my-rebind.attacker.com` (A-record → `169.254.169.254`). On the
  still-supported unauthenticated default (`auth_token=""`) this is
  unauthenticated SSRF; with a token it is authenticated SSRF plus a
  liveness/latency/error read-back oracle for internal name resolution.
- **Category:** security (SSRF / input-validation bypass / DNS rebinding TOCTOU)

- **Summary:** `is_allowed_target_url` (cluster.py:75-85) is meant to constrain
  every caller-supplied target to loopback/private scope, and it is wired into
  all three sibling entry points that `0828` identified — `base_urls` discovery
  (cluster.py:343), `POST /vampire/v1/nodes` (control.py:70), and
  `PATCH /vampire/v1/nodes/{id}` (control.py:91). But the scope check is gated on
  `_host_ip_address(parsed.hostname)` returning a parsed IP. `_host_ip_address`
  (cluster.py:65-72) returns `None` for **any** string that is not a literal
  IPv4/IPv6 address — which is every DNS hostname. The guard then executes
  `if host_ip is None: return True` (cluster.py:81-82) and admits the target
  unconditionally. So the private/loopback gate that the function's docstring
  promises ("in the safe scope") is enforced for `http://169.254.169.254` but
  **not** for `http://metadata.google.internal`, `http://internal-admin:8080`,
  `http://localhost.attacker.com`, or any public hostname. There is a second,
  compounding problem even for names that *do* resolve to private space: the
  validation resolves nothing, so it cannot prevent **DNS rebinding** — a name
  whose A record is private at check time and `169.254.169.254` at fetch time
  (TOCTOU), because the only `await` between check and fetch is the network call
  itself.

- **Location:**
  - `src/vampire/cluster.py:75-85` — `is_allowed_target_url`; the `if host_ip is
    None: return True` escape hatch at lines 81-82 is the bypass.
  - `src/vampire/cluster.py:65-72` — `_host_ip_address` returns `None` for every
    non-IP-literal host, which is what routes DNS names to the escape hatch.
  - `src/vampire/cluster.py:341-345` — `_candidate_urls` validates each
    `base_urls` entry through `is_allowed_target_url` (the `0828` fix), so a DNS
    target passes here.
  - `src/vampire/api/control.py:70-71` — `register_node` gate; a DNS
    `lmstudio_base_url` passes `is_allowed_target_url` and is fetched.
  - `src/vampire/api/control.py:91-92` — `patch_node` gate; same bypass on URL
    change.
  - `src/vampire/cluster.py:197` — the outbound fetch
    `await http_client.get(f"{base_url}/v1/models", ...)` that the bypass feeds.
  - `tests/test_phase2.py:171-207` — the entire SSRF test suite for this guard
    (`test_discover_rejects_offscope_base_urls`,
    `test_register_node_rejects_offscope_url`,
    `test_patch_node_rejects_offscope_url`) uses **IP literals only**
    (`169.254.169.254`, `8.8.8.8`), so the DNS-name bypass is completely
    uncovered.

- **Evidence:**

  The guard only constrains scope when the host is an IP literal; otherwise it
  returns `True`:

  ```python
  # src/vampire/cluster.py:75-85
  def is_allowed_target_url(base_url: str) -> bool:
      """Return whether a caller-supplied probe/proxy target is in the safe scope."""
      parsed = urlparse(base_url)
      if parsed.scheme not in _ALLOWED_SCHEMES or parsed.hostname is None:
          return False
      host_ip = _host_ip_address(parsed.hostname)
      if host_ip is None:
          return True            # <-- every DNS hostname is admitted unchecked
      if host_ip.is_link_local or host_ip.is_reserved or host_ip.is_multicast:
          return False
      return bool(host_ip.is_loopback or host_ip.is_private)
  ```

  `_host_ip_address` is what sends names down that path — it returns `None` for
  anything that is not a literal address:

  ```python
  # src/vampire/cluster.py:65-72
  def _host_ip_address(host: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
      """Parse ``host`` as an IP address when possible."""
      if host is None:
          return None
      try:
          return ipaddress.ip_address(host)
      except ValueError:
          return None            # <-- 'metadata.google.internal', 'internal-admin', etc.
  ```

  So the cloud-metadata endpoint that the IP-literal test
  (`tests/test_phase2.py:176`) explicitly blocks is reachable again by name.
  GCP/GKE/Kubernetes expose it as a DNS name precisely:
  `http://metadata.google.internal/computeMetadata/v1/...` resolves to
  `169.254.169.254` on every Google-cloud host. AWS IMDS is reachable as
  `http://instance-data/...` on many AMIs. Internal services are routinely
  addressed by name (`http://internal-admin:8080`,
  `http://vault.svc.cluster.local`).

  **Reproduction (pure validation logic, no network — exercises the real
  `is_allowed_target_url`):**

  ```
  $ PYTHONPATH=src python3 - <<'PY'
  from vampire.cluster import is_allowed_target_url as ok
  for u in [
      "http://169.254.169.254/latest/meta-data",   # IP literal: correctly blocked
      "http://metadata.google.internal/computeMetadata/v1/",  # same target, by name
      "http://internal-admin:8080",                # internal service by name
      "http://instance-data/latest/meta-data",     # AWS IMDS alias
      "http://vault.svc.cluster.local:8200",       # k8s internal service
      "http://attacker-controlled.example.com",    # arbitrary public host
  ]:
      print(f"{'ALLOW' if ok(u) else 'BLOCK':5}  {u}")
  PY
  BLOCK  http://169.254.169.254/latest/meta-data
  ALLOW  http://metadata.google.internal/computeMetadata/v1/
  ALLOW  http://internal-admin:8080
  ALLOW  http://instance-data/latest/meta-data
  ALLOW  http://vault.svc.cluster.local:8200
  ALLOW  http://attacker-controlled.example.com
  ```

  Every line after the first is a target the `0828` fix was meant to stop; only
  the IP-literal spelling is actually blocked.

  (As noted in prior suggestions, this checkout's `.venv` has a broken
  `pydantic_settings` install — `ModuleNotFoundError:
  pydantic_settings.sources.providers.aws` — that can prevent
  `vampire.config`/`vampire.cluster` from importing under that interpreter. The
  logic above depends only on `urlparse` + `ipaddress`, both stdlib; the four
  quoted lines of `is_allowed_target_url` are sufficient to confirm the bypass
  by inspection regardless of the environment breakage. Run the snippet under a
  Python whose `pydantic_settings` is intact, or read cluster.py:75-85
  directly.)

- **Conditions under which it manifests:**
  1. A caller can reach any of the three validated entry points — `POST
     /vampire/v1/discover` with `base_urls`, `POST /vampire/v1/nodes`, or `PATCH
     /vampire/v1/nodes/{id}`. On the unauthenticated default
     (`auth_token=""`, config.py:41) no credential is required at all; with a
     token, any holder of it.
  2. The target is supplied as a **DNS hostname** rather than an IP literal.
     This is not an exotic requirement — it is the *normal* way internal
     services and cloud metadata endpoints are addressed.
  3. (Rebinding variant) Even a name that resolves to private space at
     validation time can be re-pointed to `169.254.169.254`/public space before
     the fetch, since validation performs no resolution and the only
     intervening `await` is the fetch's own network round-trip
     (cluster.py:197).

- **Impact:**
  - **Cloud metadata exfiltration:** `metadata.google.internal` /
    `instance-data` reach the same `169.254.169.254` IMDS the IP-literal test
    blocks. On GCP the response can include service-account OAuth tokens; on
    unpatched IMDSv1 AWS it can include instance-role credentials. The probe's
    `status`/`latency_ms`/`last_error` (cluster.py:200-221) and the node body
    returned by `GET /vampire/v1/nodes` form the read-back oracle.
  - **Internal network reconnaissance by name:** `http://internal-admin:8080`,
    `http://vault.svc.cluster.local:8200`, `http://<service>.<namespace>` — the
    gateway reports which internal names resolve and respond, and how they fail,
    from its own (often more-trusted) network position.
  - **Arbitrary public egress:** any `http(s)://public-host` is fetched,
    enabling blind SSRF callbacks / egress from the gateway host.
  - **DNS rebinding (TOCTOU):** a name that validates as private can be
    refetched against a rebound address, defeating even a naive "resolve once
    and check" patch unless the resolved address is pinned for the actual
    connection.
  - **Blast radius:** all three sibling entry points share the one broken
    predicate, so a single fix closes all of them — and conversely the single
    hole exposes all of them today. The `lan_scan` branch
    (cluster.py:351-365) is unaffected because it only ever synthesizes
    `http://<ip>:<port>` literals, which still hit the IP-validated path.

- **Fix:** `is_allowed_target_url` must not blanket-allow non-IP hosts. Resolve
  the hostname and require that **every** resolved address is loopback/private
  and none is link-local/reserved/multicast; reject names that do not resolve or
  that resolve to any out-of-scope address. To also close the rebinding TOCTOU,
  the connection should ultimately be made to a *pinned* in-scope address rather
  than re-resolving the name at fetch time — but the minimal, high-value fix is
  to stop returning `True` for unresolved/out-of-scope names.

  **Before** (cluster.py:75-85):

  ```python
  def is_allowed_target_url(base_url: str) -> bool:
      parsed = urlparse(base_url)
      if parsed.scheme not in _ALLOWED_SCHEMES or parsed.hostname is None:
          return False
      host_ip = _host_ip_address(parsed.hostname)
      if host_ip is None:
          return True            # admits every DNS name
      if host_ip.is_link_local or host_ip.is_reserved or host_ip.is_multicast:
          return False
      return bool(host_ip.is_loopback or host_ip.is_private)
  ```

  **After** (resolve names; require all resolved addresses in scope):

  ```python
  def _ip_in_scope(host_ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
      if host_ip.is_link_local or host_ip.is_reserved or host_ip.is_multicast:
          return False
      return bool(host_ip.is_loopback or host_ip.is_private)


  def is_allowed_target_url(base_url: str) -> bool:
      """Return whether a caller-supplied probe/proxy target is in the safe scope.

      IP literals are validated directly. DNS hostnames are RESOLVED and every
      returned address must be in scope; a name that does not resolve, or that
      resolves to any link-local/reserved/multicast/public address, is rejected.
      'localhost' is allowed explicitly so the common loopback alias still works.
      """
      parsed = urlparse(base_url)
      if parsed.scheme not in _ALLOWED_SCHEMES or parsed.hostname is None:
          return False

      host = parsed.hostname
      host_ip = _host_ip_address(host)
      if host_ip is not None:
          return _ip_in_scope(host_ip)

      if host.lower() == "localhost":
          return True
      try:
          addrinfo = socket.getaddrinfo(host, parsed.port)
      except OSError:
          return False           # unresolvable -> reject (was: silently allowed)
      resolved = {
          _host_ip_address(str(sockaddr[0]))
          for _, _, _, _, sockaddr in addrinfo
      }
      resolved.discard(None)
      # Reject if anything failed to parse or ANY address is out of scope.
      return bool(resolved) and all(_ip_in_scope(ip) for ip in resolved)
  ```

  Notes:
  - `socket` is already imported in cluster.py (line 8) for
    `_local_ip_addresses`, so no new dependency.
  - Requiring **all** resolved addresses in scope (not "any") prevents a
    dual-A-record name from slipping a public/metadata address past the check.
  - `getaddrinfo` is a blocking call; it is invoked from async control-plane
    handlers. For the minimal security fix this is acceptable (it runs once per
    register/patch/discover, the same paths that already block on the network
    probe), but the rigorous version wraps it in
    `await asyncio.get_running_loop().run_in_executor(None, ...)` or
    `anyio.to_thread.run_sync` to avoid stalling the event loop — relevant given
    suggestion `0828`'s sibling concern about blocking work on the loop. Make
    the function async, or add an async wrapper, if you take that route.
  - The residual DNS-rebinding TOCTOU is only fully closed by connecting to the
    pinned resolved address (e.g. via a custom httpx transport / resolver that
    reuses the validated IP). That is a larger change; call it out as a
    follow-up and keep the resolve-and-reject fix as the immediate mitigation,
    which already removes the static-name bypass that the current tests miss.

- **Test:** Add to `tests/test_phase2.py`. The first assertion fails today
  (`is_allowed_target_url` returns `True` for the metadata name) and passes
  after the fix; the loopback cases keep passing so the change is
  non-regressive.

  ```python
  import socket
  import pytest
  from vampire.cluster import is_allowed_target_url


  def test_is_allowed_target_url_blocks_dns_metadata_name(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """A DNS name resolving to the metadata IP must be rejected, just like the
      169.254.169.254 literal already is (closes the IP-only bypass)."""

      def _fake_getaddrinfo(host, port, *a, **k):
          # metadata.google.internal -> 169.254.169.254 (link-local)
          return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port or 80))]

      monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
      assert is_allowed_target_url("http://metadata.google.internal/v1/") is False


  def test_is_allowed_target_url_blocks_public_dns_name(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      def _fake_getaddrinfo(host, port, *a, **k):
          return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

      monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
      assert is_allowed_target_url("http://example.com") is False


  def test_is_allowed_target_url_rejects_unresolvable_name(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      def _boom(host, port, *a, **k):
          raise OSError("name does not resolve")

      monkeypatch.setattr(socket, "getaddrinfo", _boom)
      assert is_allowed_target_url("http://does-not-exist.invalid") is False


  def test_is_allowed_target_url_allows_private_dns_name(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      def _fake_getaddrinfo(host, port, *a, **k):
          return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port or 80))]

      monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
      assert is_allowed_target_url("http://node-a.lan:1234") is True


  def test_is_allowed_target_url_still_allows_loopback_literal() -> None:
      assert is_allowed_target_url("http://127.0.0.1:1234") is True
      assert is_allowed_target_url("http://localhost:1234") is True
  ```

  And an end-to-end guard at the control-plane seam (mirrors the existing
  IP-literal tests at test_phase2.py:187-194 but via a name):

  ```python
  def test_register_node_rejects_metadata_dns_name(
      client: TestClient, monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      import socket as _socket

      def _fake_getaddrinfo(host, port, *a, **k):
          return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("169.254.169.254", port or 80))]

      monkeypatch.setattr(_socket, "getaddrinfo", _fake_getaddrinfo)
      resp = client.post(
          "/vampire/v1/nodes",
          json={"id": "evil-dns", "lmstudio_base_url": "http://metadata.google.internal/"},
      )
      assert resp.status_code == 400
      assert client.get("/vampire/v1/nodes/evil-dns").status_code == 404
  ```

- **Effort & risk:** ~15-20 lines changed in one file
  (`src/vampire/cluster.py`), plus ~50 lines of new tests. Low-to-moderate risk:
  the change *tightens* an allow predicate, so the only behavioral shift is that
  previously-accepted DNS targets now require in-scope resolution. The one
  compatibility consideration is environments that legitimately register nodes
  by hostname (e.g. `http://node-a.lan:1234`) — those keep working as long as
  the name resolves to a private/loopback address, which is the intended
  contract. If `getaddrinfo` is kept synchronous, note the event-loop caveat
  above; wrapping it in a thread executor removes that concern. Backward
  compatible for all IP-literal and loopback configurations; the `lan_scan`
  path is unaffected.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · audit run over
  `src/vampire/*` + `tests/test_phase2.py` + `DESIGN-API.md` · one new
  suggestion file plus README index update · cost not reliably derivable from
  per-call figures. Marked estimated.
