# Control-API bearer check uses non-constant-time comparison, leaking the gateway token via timing

- **Severity:** High — the *privileged* control surface (`/vampire/v1/*`) compares the bearer token with Python's `!=`, a length-dependent, short-circuiting comparison that is exploitable as a timing side channel; the very same project already knows the right answer (`hmac.compare_digest`) and uses it one module over, so this is an inconsistent, security-regressing gap on the more dangerous surface.
- **Category:** security
- **Summary:** `vampire/api/_auth.py::require_control_auth` authenticates control-plane requests with `credentials.credentials != token`, a non-constant-time string comparison, while `vampire/auth.py::require_auth` (the OpenAI proxy surface) correctly uses `hmac.compare_digest`. The control API can create/delete nodes, rewrite routes, toggle sharing, and trigger LAN discovery, so it is the *higher*-value target, yet it is the one guarded by the leaky comparison. An attacker who can measure response latency can recover the token byte-by-byte and then take over cluster orchestration.
- **Location:**
  - `src/vampire/api/_auth.py:23` (the offending comparison).
  - Contrast / contract reference: `src/vampire/auth.py:42` (the correct constant-time comparison).
  - Affected router (everything this guards): `src/vampire/api/control.py:27-31` plus all node/route/discovery/share handlers below it.

## Evidence

The control-plane auth dependency:

```python
# src/vampire/api/_auth.py
15  async def require_control_auth(
16      credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
17  ) -> None:
18      token = get_settings().auth_token
19      if not token:
20          return
21      if credentials is None or credentials.scheme.lower() != "bearer":
22          raise _auth_error()
23      if credentials.credentials != token:      # <-- non-constant-time comparison
24          raise _auth_error()
```

Compare with the sibling proxy-auth module, which the project authored to do exactly this correctly:

```python
# src/vampire/auth.py
38      header = request.headers.get("authorization", "")
39      scheme, _, presented = header.partition(" ")
40      if scheme.lower() != "bearer" or not presented:
41          raise AuthError("Missing bearer token.")
42      if not hmac.compare_digest(presented, token):   # <-- constant-time, correct
43          raise AuthError("Invalid bearer token.")
```

The contract being violated is: *secret comparisons in an authentication path must be constant-time with respect to the secret.* It is honored at `auth.py:42` and broken at `_auth.py:23`.

**Why `!=` leaks information.** CPython's `str.__eq__` (`unicode_compare_eq` / `unicode_eq` in `Objects/unicodeobject.c`) first compares length, and for equal-length strings does a `memcmp`-style scan that **returns at the first differing byte**. Therefore the time to evaluate `credentials.credentials != token` is a function of the length of the shared prefix between the attacker's guess and the real token:

1. The attacker hits any control route, e.g. `GET /vampire/v1/status`, with `Authorization: Bearer <guess>`.
2. For each candidate first byte `b` in the token alphabet, the attacker sends `Bearer b\x00\x00...` (padded to the observed/guessed length) many times and records the response-latency distribution.
3. The guess whose mean/percentile latency is measurably higher matched one more byte before the comparison short-circuited; that byte is fixed.
4. Repeat for byte 2, 3, … The search collapses from O(alphabet^len) brute force to O(alphabet × len) — a few thousand requests per byte instead of astronomically many.

The signal per comparison is small (tens of nanoseconds), but it is amplified by (a) sending each guess thousands of times and using robust statistics (median / trimmed mean / Kocher-style difference-of-distributions), and (b) the fact that the control API performs *no other secret-dependent work before the comparison* on the cheap `/status` route — `status()` at `control.py:35` just reads an in-memory list — so the comparison is a clean, isolated timing target with very little surrounding noise. Over a LAN (the explicit deployment model per `METHOD-A.md`), round-trip jitter is low enough to make this practical; the gateway is designed to be reachable by other machines on the subnet (see the `lan_scan` discovery in `cluster.py:263-274`).

**Length oracle, additionally.** Because `str.__eq__` compares length first, unequal-length guesses short-circuit even earlier and with a distinct timing profile, giving the attacker a separate oracle to recover the token *length* before attacking content. `hmac.compare_digest` is specifically hardened against both the content and (for equal-length inputs) the early-exit leak.

**No test pins this behavior.** A content search of `tests/` for `compare_digest`, `credentials.credentials`, `require_control_auth`, and `require_auth` returns zero matches, so nothing prevents this from silently regressing or blocks a future refactor from "simplifying" `auth.py:42` back to `!=` to "match" the control module. The auth contract is entirely unguarded by tests.

## Impact

- **What an attacker observes/gains:** With latency measurements against any `/vampire/v1/*` route, an on-LAN (or co-located, or reverse-proxied-with-tight-jitter) attacker recovers `VAMPIRE_AUTH_TOKEN` without ever seeing a `200`. Once recovered, they hold full control-plane authority: `POST /vampire/v1/nodes` to register attacker-controlled LM Studio endpoints, `POST /vampire/v1/routes` to repoint `vampire:auto` traffic at a malicious node (model-output/prompt exfiltration), `POST /vampire/v1/discover` to drive the gateway into scanning the owner's LAN, and `POST /vampire/v1/share` to flip sharing state.
- **Blast radius:** the entire cluster the gateway fronts. Because routing rewrites the downstream `model` and base URL (`openai_compat.py:132-145`), a poisoned route silently MITMs every routed completion — prompts and responses flow through attacker infrastructure.
- **When it triggers:** only when `auth_token` is configured (the intended hardened deployment). Ironically, operators who *enable* auth are the ones exposed to this particular leak; the unauthenticated default is unaffected, so this hits exactly the security-conscious users.
- **Why it's High not Critical:** exploitation requires many timed requests and a relatively low-jitter network path, and the token alphabet/length are operator-chosen (a long, high-entropy token raises the request budget). It is not a one-shot bypass, but it is a real, well-understood class of vulnerability on the most privileged surface, with a trivially correct fix already present elsewhere in the codebase.

## Fix

Use `hmac.compare_digest` (constant-time) for the control-plane comparison, mirroring `auth.py`. `compare_digest` accepts two `str` of ASCII or two `bytes`; both `credentials.credentials` and `token` are `str`, so it is a drop-in.

**Before** (`src/vampire/api/_auth.py`):

```python
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from vampire.config import get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_control_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    token = get_settings().auth_token
    if not token:
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error()
    if credentials.credentials != token:
        raise _auth_error()
```

**After:**

```python
from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from vampire.config import get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_control_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    token = get_settings().auth_token
    if not token:
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error()
    # Constant-time comparison: avoid leaking the token via timing, matching
    # vampire.auth.require_auth (the OpenAI-proxy surface).
    if not hmac.compare_digest(credentials.credentials, token):
        raise _auth_error()
```

Notes / invariants to preserve:
- Keep the early `if not token: return` (unauthenticated default) and the scheme/None checks exactly as-is — those branch on non-secret data and are fine to short-circuit.
- `compare_digest` on two `str` raises `TypeError` only for non-ASCII; tokens are operator-chosen ASCII secrets. If you want to be defensive against a non-ASCII configured token, compare on bytes: `hmac.compare_digest(credentials.credentials.encode(), token.encode())`. The `auth.py` sibling compares `str`, so matching that keeps the two modules consistent.
- No `# type: ignore` is involved; no public behavior changes for valid/invalid tokens (same 401 envelope, same `WWW-Authenticate: Bearer`). Only the *timing* of the reject path changes.
- Consider a follow-up to factor a single shared `verify_token(presented: str, token: str) -> bool` helper used by both `auth.py` and `_auth.py` so the constant-time guarantee cannot drift between the two surfaces again. (Out of scope for the minimal fix, but it is the root cause of the divergence.)

## Test

A timing test is inherently flaky in CI, so the durable regression test asserts the *implementation contract* — that the comparison routes through `hmac.compare_digest` — plus the behavioral contract that a wrong token is rejected. The first assertion fails today (because `_auth.py` never imports or calls `hmac.compare_digest`) and passes after the fix.

```python
# tests/test_control_auth_constant_time.py
import hmac

import pytest
from fastapi.security import HTTPAuthorizationCredentials

import vampire.api._auth as control_auth
from vampire.api._auth import _auth_error, require_control_auth
from vampire.config import Settings


@pytest.fixture
def configured_token(monkeypatch):
    # Force a configured gateway token regardless of ambient env.
    monkeypatch.setattr(
        control_auth, "get_settings", lambda: Settings(auth_token="s3cret-token")
    )
    return "s3cret-token"


@pytest.mark.asyncio
async def test_control_auth_uses_constant_time_compare(configured_token, monkeypatch):
    """The control-plane check must compare the token via hmac.compare_digest."""
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    # Patch the name the module actually calls.
    monkeypatch.setattr(control_auth.hmac, "compare_digest", spy)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="s3cret-token")
    await require_control_auth(creds)  # valid token -> no raise

    # FAILS TODAY: compare_digest is never invoked because _auth.py uses `!=`.
    assert calls, "control auth must use hmac.compare_digest for the token check"
    assert calls[-1] == ("s3cret-token", "s3cret-token")


@pytest.mark.asyncio
async def test_control_auth_rejects_wrong_token(configured_token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
    with pytest.raises(type(_auth_error())):  # HTTPException(401)
        await require_control_auth(creds)


@pytest.mark.asyncio
async def test_control_auth_open_when_unconfigured(monkeypatch):
    monkeypatch.setattr(control_auth, "get_settings", lambda: Settings(auth_token=""))
    await require_control_auth(None)  # no token configured -> allowed
```

(If the project prefers a pure behavioral test, an integration variant using `TestClient(create_app())` with `VAMPIRE_AUTH_TOKEN` set can assert `401` for a wrong token and `200` for the right one on `GET /vampire/v1/status`; but only the `compare_digest`-spy assertion above actually fails *today*, which is the point — it pins the constant-time contract that is currently unenforced.)

## Effort & risk

- **Lines changed:** ~3 in `src/vampire/api/_auth.py` (add `import hmac`, swap the comparison, add a comment). New test file ~50 lines.
- **Files touched:** `src/vampire/api/_auth.py` (fix) + `tests/test_control_auth_constant_time.py` (new). Optional follow-up touches `src/vampire/auth.py` if you extract a shared helper.
- **Backward-compat:** none broken. Identical 401/200 semantics, identical headers and error envelope; only the reject-path timing changes. No config, no API, no docs surface changes required (though a one-line note in any security/auth doc that *both* surfaces are constant-time would be worth adding if such a doc exists).

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~142000 tok · output ~3200 tok · est. cost ~$2.37 · run started 17:00 finished 17:02.
