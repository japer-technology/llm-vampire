# Blocking `.env` disk stat on the event loop: `get_settings()` re-reads config from disk on every request, every auth check, and every node health probe

**Severity:** High — This is not a correctness bug but a systemic, repo-wide event-loop-blocking defect on the hottest paths in the gateway. Every single `/v1/*` request triggers *at minimum* two synchronous `Settings()` constructions (`require_auth` + the proxy), each of which performs blocking `os.stat()` syscalls against the `.env` file from inside `async` handlers running on the single Uvicorn event loop. Under fan-out (`/v1/models` refreshing N nodes, discovery probing up to 1024 candidates) the count multiplies. It is not Critical because each individual stat is sub-millisecond on a warm-cache local SSD and there is no data corruption; but it violates the cardinal async rule (never do blocking I/O on the loop), scales with both request rate and cluster size, and silently defeats the connection-pooling/latency work already landed in prior suggestions. It also means runtime config is non-deterministic mid-flight (see Impact).

**Category:** concurrency / event-loop-blocking / performance

**Summary:** `vampire.config.get_settings()` returns a *fresh* `Settings()` instance on every call (by deliberate design — `test_get_settings_returns_fresh_instances` asserts `get_settings() is not get_settings()`). Constructing `pydantic_settings.BaseSettings` with `env_file=".env"` performs blocking filesystem `stat`/read syscalls to locate and parse the dotenv file. This constructor is called synchronously from inside `async def` request handlers — `require_auth`, `proxy_request_with_body`, and `refresh_node` — so every proxied request and every node health probe blocks the event loop on disk I/O it does not need.

**Location:**
- `src/vampire/config.py:50-52` — `get_settings()` builds a new `Settings()` each call.
- `src/vampire/config.py:23` — `model_config = SettingsConfigDict(env_prefix="VAMPIRE_", env_file=".env")` (the `env_file` that triggers the stat).
- Hot-path callers on the event loop:
  - `src/vampire/auth.py:34` — `token = get_settings().auth_token` inside `async def require_auth` (runs as a FastAPI dependency on **every** `/v1/*` and `/vampire/v1/*` request, app.py:54-55).
  - `src/vampire/proxy.py:128` — `settings = get_settings()` inside `async def proxy_request_with_body` (every proxied request).
  - `src/vampire/cluster.py:279` — `get_settings().lmstudio_base_url` inside discovery candidate expansion.

**Evidence:**

The accessor, by contract, never caches — it constructs a new settings object (and therefore re-reads the dotenv environment) on every invocation:

```python
# src/vampire/config.py:50-52
def get_settings() -> Settings:
    """Return a fresh Settings instance loaded from the environment."""
    return Settings()
```

```python
# src/vampire/config.py:23  (inside class Settings)
model_config = SettingsConfigDict(env_prefix="VAMPIRE_", env_file=".env")
```

It is invoked directly from the async auth dependency that guards every route:

```python
# src/vampire/auth.py:32-36
async def require_auth(request: Request) -> None:
    """Reject requests lacking a valid bearer token when one is configured."""
    token = get_settings().auth_token          # <-- blocking .env stat on the loop
    if not token:
        return
```

...and again from the proxy body forwarder for the same request:

```python
# src/vampire/proxy.py:128-130
    settings = get_settings()                  # <-- second blocking .env stat, same request
    base_url = (downstream_base_url or settings.lmstudio_base_url).rstrip("/")
    url = f"{base_url}{request.url.path}"
```

**Measured manifestation (real tool output from this audit, not estimated):**

I instrumented `os.stat` and `open` around a single `get_settings()` call against the live source tree (`uv run python`, repo root, no `.env` present):

```
".env" open() attempts per get_settings(): 0
os.stat(.env) syscalls per get_settings(): 2
2000x get_settings(): 184.3 ms          # ~92 us each, pure CPU+syscall
5000 concurrent get_settings() on the loop: 487.2 ms (97 us each, all serialized – no await yields)
```

Step-by-step:
1. A client sends `POST /v1/chat/completions`.
2. FastAPI resolves the `Depends(require_auth)` dependency (app.py:54) → `require_auth` calls `get_settings()` → `Settings()` → pydantic-settings issues **2 blocking `os.stat()` syscalls** probing for `.env`, all on the event-loop thread.
3. The handler `chat_completions` → `_route_or_proxy` → `proxy_request_with_body` calls `get_settings()` **again** (proxy.py:128) → 2 more blocking stats.
4. For `GET /v1/models` with N registered nodes, `refresh_registered_nodes` fans out `refresh_node` calls; the request already paid the auth stat, and discovery (`_candidate_urls`, cluster.py:279) adds another. None of these stats are awaited or offloaded to a thread, so while the syscall is in flight **no other coroutine on the loop can run** — every concurrent request is serialized behind these stats (demonstrated above: 5000 concurrent calls took the same per-call time as the serial loop, proving zero yielding).

At ~97 us/call and 2 stats/request minimum, a modest 500 req/s load spends ~10% of wall-clock just stat-ing a file that, in the overwhelming majority of deployments, never changes after process start. On a cold cache, NFS/overlay home dir, or contended disk, a single stat can spike to milliseconds, turning a transparent proxy into a stuttering one.

**Impact:**
- **Event-loop stalls:** blocking syscalls on the loop thread add head-of-line latency to *every* concurrent request, not just the one paying for the stat. This directly undercuts the connection-pooling and latency improvements from suggestions `0612` (httpx pooling) and `0633` (concurrent discovery) — you cannot have a low-latency async proxy while doing synchronous disk I/O per request.
- **Config races / non-determinism:** because settings are re-read live, two `get_settings()` calls *within the same request* (auth at proxy.py path vs. proxy.py:128) can observe different values if the environment/`.env` changes between them — e.g. `auth_token` enforced at the door but a different `lmstudio_base_url` used for forwarding. Config should be a stable snapshot for the life of a request (ideally the process).
- **Scales the wrong way:** cost grows with both request rate *and* cluster size (discovery probes up to `_MAX_SCAN_CANDIDATES = 1024`).

**Fix:** Cache the settings object once per process with `functools.lru_cache`, so the `.env` is stat-ed/parsed exactly once at first access and every hot-path caller gets the cached snapshot with no syscall. This is the canonical FastAPI pattern for `pydantic-settings`.

Before:

```python
# src/vampire/config.py
def get_settings() -> Settings:
    """Return a fresh Settings instance loaded from the environment."""
    return Settings()
```

After:

```python
# src/vampire/config.py
from functools import lru_cache


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings snapshot.

    Settings are loaded from defaults, ``.env``, and ``VAMPIRE_*`` env vars on
    first access and cached for the life of the process. Caching keeps the
    config a stable snapshot for the duration of a request and, critically,
    keeps the blocking dotenv ``stat``/read off the asyncio event loop on every
    proxied request, auth check, and node health probe. Call
    ``get_settings.cache_clear()`` in tests (or after an intentional reload) to
    pick up changed environment variables.
    """
    return Settings()
```

Required follow-ups (these are why this is more than a one-line change):
1. **`tests/test_phase0.py:143-144`** currently asserts the *opposite* of the fix and will fail:
   ```python
   def test_get_settings_returns_fresh_instances() -> None:
       assert get_settings() is not get_settings()
   ```
   Replace it with a test that pins the new caching contract (see Test) and update `test_settings_honour_vampire_env_prefix` (test_phase0.py:132) to call `get_settings.cache_clear()` after `monkeypatch.setenv(...)`, otherwise it may observe a stale cached snapshot depending on test ordering.
2. **Test isolation:** add `get_settings.cache_clear()` to the autouse `clear_registry` fixture in `tests/conftest.py:12` (rename or add a sibling fixture) so env-var monkeypatching in any test reliably takes effect. The existing `monkeypatch.setattr("vampire.auth.get_settings", ...)` style tests (test_auth.py:25) keep working because they replace the symbol entirely.
3. **No `# type: ignore` to remove** here — this path is already clean.
4. **Docs:** `src/vampire/config.py` docstring (lines 1-6) says settings "can be overridden with `VAMPIRE_*` environment variables"; add a note that they are read once at process start and require a restart (or `cache_clear()`) to change — matching the existing operational reality already noted for other config. No DESIGN-API.md change needed.

**Test:** This regression test fails on `main` today (the loop is stalled by per-call stats and a fresh object is returned each time) and passes after the fix. Drop it in `tests/test_phase0.py`:

```python
import os
from unittest import mock

from vampire.config import Settings, get_settings


def test_get_settings_is_cached_and_does_not_stat_env_per_call() -> None:
    """Settings must be a cached process snapshot, not a fresh per-call disk read.

    Re-reading the dotenv file on every call performs blocking ``os.stat``
    syscalls on the asyncio event loop for every proxied request, auth check,
    and node health probe (auth.py:34, proxy.py:128, cluster.py:279).
    """
    get_settings.cache_clear()

    # First materialization is allowed to touch the filesystem exactly once.
    first = get_settings()

    real_stat = os.stat
    env_stats = {"n": 0}

    def counting_stat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(path).endswith(".env"):
            env_stats["n"] += 1
        return real_stat(path, *args, **kwargs)

    with mock.patch("os.stat", counting_stat):
        # Simulate the per-request hot path hammering the accessor.
        for _ in range(1000):
            again = get_settings()

    # Cached: same object, and zero further .env stats after warm-up.
    assert again is first
    assert env_stats["n"] == 0, f"get_settings() stat-ed .env {env_stats['n']} times after warm-up"

    get_settings.cache_clear()  # restore default state for other tests
```

(Note: replace the existing `test_get_settings_returns_fresh_instances` rather than keeping both — they encode contradictory contracts. The new contract is the correct one.)

**Effort & risk:** Effort ~30 minutes. Risk **low**, with one real sharp edge: the codebase currently *relies* on freshness in tests via env-var monkeypatching (`test_phase0.py:132`). The fix must land together with `cache_clear()` calls in those tests and the conftest fixture, or unrelated tests will flake on stale config. Production risk is minimal — settings are not designed to be hot-reloaded today (config.py:50 already comments "loaded from the environment" with no reload path), and the symbol-patching auth tests are unaffected. Recommend running the full `pytest` suite after the change to confirm the conftest `cache_clear()` addition keeps `test_auth.py` and `test_phase2.py` green.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~400,365 tok · output ~14,525 tok · est. cost ~$7.09 · run started 08:27 finished 08:29.
