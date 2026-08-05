# Security Design Thesis — Consent, Tiering, and Metering

This is the rigorous, metaphor-free treatment of the consent and contribution
model for `llm-vampire`. The same thesis is told in the project's folklore
register in [`vampire.md`](vampire.md) and in a Star Trek register in
[`startrek.md`](startrek.md); this document is the normative reference. It builds
on the LM Studio authentication model
([`../lmstudio.ai/06-authentication.md`](../lmstudio.ai/06-authentication.md)) and
the mechanism mapping
([`../lmstudio.ai/12-vampire-integration.md`](../lmstudio.ai/12-vampire-integration.md)).

Status: **design-stage proposal.** No monetization, credit, or settlement
primitive exists in the codebase today; this document specifies the intended
model so that implementation has a target.

---

## 1. Threat and trust model

Vampire is an aggregation overlay in front of many independently-owned LM Studio
nodes. The security-relevant facts about a node are fixed by LM Studio, not by
Vampire:

- A fresh LM Studio server is **unauthenticated** and bound to `127.0.0.1`. The
  owner must deliberately enable **Serve on Local Network** to expose it, and LM
  Studio recommends enabling authentication whenever it is exposed beyond
  localhost.
- API tokens are **owner-chosen free-text strings**, carried in the standard
  bearer `Authorization` header, with per-token permissions, shown once, and
  editable or deletable by the owner at any time.

Two trust boundaries therefore exist and **must not be conflated**:

| Layer | Credential | Trusts | Purpose |
| --- | --- | --- | --- |
| **Node layer** | LM Studio token (owner-set) | Vampire → node | Owner consent + per-node permissions |
| **Client layer** | Vampire realm token (Vampire-set) | Client → Vampire | Identity, authorization, accounting |

The contribution model lives in the **node layer**. Identity and metering live in
the **client layer**. Mixing them is the principal design error to avoid.

## 2. Consent is affirmative and explicit

Network reachability is **not** consent. An exposed but unconfigured node is a
bystander: Vampire may technically reach it, but reachability alone must not
trigger contribution accounting or grant any benefit.

Consent is signalled **affirmatively** by the owner setting a recognised token
value. This makes monetization strictly opt-in and aligns with the project's
governing principle: *governed private inference, not uncontrolled peer-to-peer
sharing.*

> **Invariant C1.** No credit accrues, and no contribution benefit is granted,
> unless the node presents a recognised opt-in token. Absence of a token means
> *use-if-exposed but never account*.

## 3. The opt-in policy tag — `vampire<NN>`

The opt-in signal is a **policy tag** encoded in the LM Studio token value:

| Token value | Declared policy |
| --- | --- |
| *(unset)* | No opt-in. No accounting, no benefit. |
| `vampire` | Consent; utilisation ceiling 100% while idle. |
| `vampire50` | Consent; utilisation ceiling 50%. |
| `vampire32` | Consent; utilisation ceiling 32%. |
| `vampire8` | Consent; utilisation ceiling 8%. |

Recommended canonical form: `vampire<NN>` where `NN` is an integer percentage
(`0–100`); a parser of the form `^vampire(\d{1,3})?$` accepts the whole family,
with bare `vampire` meaning `100`.

The chief advantage is **zero upstream change**: it works on stock LM Studio
because the owner can already set any token string. The chief hazard follows in
§4.

## 4. A public tag is a label, not a credential

If the `vampire<NN>` tags are a **published convention**, they are by definition
**not secret**. Any party that knows the convention can present `vampire50`.

> **Invariant C2.** A recognised policy tag MUST be treated as a public label that
> conveys *consent and a utilisation ceiling only*. It MUST NOT be relied upon for
> authentication or to exclude unauthorized callers.

Consequences:

- A node whose token is a bare public tag is, for access-control purposes, an
  **open node**. On an untrusted network (e.g. shared corporate Wi-Fi) any host
  can reach it. This is acceptable *only* if the owner intends an open
  contribution; it is not a security control.
- Attribution of credit **cannot** be based on "presented the tag," because the
  tag is public. Attribution MUST be based on the authenticated **client-layer**
  identity of the Vampire performing the routing (§6).

### Two-part tokens (policy + secret)

An owner who needs both a real credential *and* a declared tier SHOULD use a
two-part token of the form `vampire<NN>:<secret>`:

- Prefix `vampire<NN>` — public policy label (parsed by Vampire for the ceiling).
- Suffix `<secret>` — the genuine shared secret that actually gates access.

Vampire stores the full string in its per-node token vault and forwards it
verbatim; it parses only the prefix for policy. Changing the prefix re-tiers;
changing the suffix re-keys. Vampire MUST NOT log or expose the suffix.

## 5. Consent is mutable and revocable

LM Studio tokens are editable and deletable at any time, so the policy tag is
**live owner state**, not a registration-time constant. Vampire MUST treat it as
such.

- **Re-tiering:** `vampire50` → `vampire8` lowers the ceiling; `vampire8` →
  `vampire` raises it.
- **Revocation:** deleting the token (or replacing it with a non-recognised value)
  withdraws consent. Persistent `401/403` MUST be treated as *node withdrew
  consent* and the node removed from rotation.

> **Invariant C3.** Vampire MUST re-read the policy tag on its regular refresh
> cycle and MUST NOT cache a tier across the interval in which it could change.
> Policy is interrogated, not assumed.

## 6. Metering and attribution

Because the policy tag is public (§4), metering MUST be anchored in the
**client layer**:

1. Each routing decision is performed by an authenticated Vampire instance with a
   known identity (its own realm/credentials toward the consuming business or
   client).
2. The contribution ledger attributes the work to the **node owner** (the
   provider) and the consumption to the **authenticated client** (the payer),
   using Vampire's own request records — not the node token.
3. The node's declared tier (§3) bounds *how much* work the node may be given; the
   ledger records *how much was actually given* for settlement.

> **Invariant C4.** Credit MUST be computed from Vampire's authenticated,
> server-side request accounting (audit log), never from possession of the public
> policy tag.

### Time-segmented accounting

Because tiers can change mid-session (§5), the ledger MUST be **segmented by the
tier in force during each interval**:

- Work performed under `vampire50` is credited under the 50% policy; if the owner
  switches to `vampire8` at time *t*, work after *t* is credited under 8%.
- Tier changes are **effective-from**, never retroactive.

## 7. Enforcement of the utilisation ceiling

The tag expresses *intent*; LM Studio does **not** enforce it (it will serve 100%
if asked). Enforcement is Vampire's responsibility:

- The scheduler MUST cap the node's utilisation (duty cycle / rate / concurrency)
  at the declared ceiling while the node is eligible.
- On a **downward** tier change, Vampire MUST apply the new, lower ceiling to
  **in-flight** work — throttling or gracefully draining — not merely to future
  requests. The ceiling is a live constraint, not a promise about the future.
- "Utilisation" MUST be defined precisely and documented (e.g. share of
  wall-clock busy time vs. concurrent-request count); these differ materially for
  an interactive machine and MUST NOT be used interchangeably.

> **Invariant C5.** The declared ceiling is enforced by Vampire's scheduler, binds
> in-flight work on downward changes, and is honour-system only to the extent the
> routing Vampire is trusted. In multi-Vampire or mesh deployments, signed node
> registration and per-node policy become mandatory (not optional), because every
> forwarding party must be trusted to respect the ceiling.

## 8. Interaction with owner-activity / idle gating

The ceiling is the maximum **while the node is eligible to contribute**.
Owner-activity detection (where the node agent provides it) gates eligibility
independently:

- When owner activity is detected, eligible utilisation drops toward **0%**
  regardless of tier — the declared tier is a ceiling on *idle* contribution, not
  a floor that overrides the owner's live use of their own machine.
- When the node returns to idle, contribution may rise again up to the declared
  ceiling.

## 9. Summary of invariants

- **C1 — Affirmative consent.** No accounting or benefit without a recognised
  opt-in token; reachable ≠ consenting.
- **C2 — Label, not credential.** A public policy tag conveys consent + ceiling
  only; never an access control.
- **C3 — Live policy.** Re-read the tag each cycle; never cache a tier across a
  window in which it can change.
- **C4 — Client-layer metering.** Attribute credit from authenticated server-side
  accounting, not from possession of the public tag.
- **C5 — Real enforcement.** The scheduler enforces the ceiling, binds in-flight
  work on downward changes, and requires signed registration once more than one
  forwarding party is involved.

These five invariants make the opt-in/tier model coherent: the token declares
*policy*, the Vampire layer provides *identity, metering, and enforcement*, and
the owner retains a *live, revocable* dial over their own consent.
