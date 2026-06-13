# The Federation Charter — Design Thesis (Star Trek register)

> *"A starship may not enter a sovereign system without invitation. Worlds are
> not annexed; they petition. Membership is freely given — and may be freely
> rescinded." — paraphrase of the Prime Directive*

This document retells the design thesis of `lmstudio-vampire` in a Star Trek
register. It is a narrative companion to [`vampire.md`](vampire.md) (the same
thesis in the project's folklore register) and to the rigorous treatment in
[`security-design-thesis.md`](security-design-thesis.md). Where this document
speaks of *petition*, *membership*, and *charter*, the security thesis speaks of
*opt-in consent*, *federation*, and *policy* — they describe the same system.

---

## 1. Worlds and the Federation

There are many **worlds** and very few instances of the **Federation**.

- A **world** is an LM Studio instance — a sovereign system with its own
  resources, running models behind an OpenAI-compatible API. Most systems on any
  network will only ever be independent worlds. People already run them.
- The **Federation** is an `lmstudio-vampire` instance. It commands no compute of
  its own. It is the thin layer that *charts, governs, routes, and coordinates*
  the worlds that have **petitioned to join**.

This asymmetry is the shape of the project: ubiquitous worlds, one slender
Federation that unites a sector of them into a single governed service. A world
provisions nothing new — it runs stock LM Studio. The Federation is the only
special construct, and one of it can coordinate an entire network.

## 2. Detected is not a member

Long-range sensors may *detect* a world — its presence known, its space charted —
without that world having **petitioned for membership**. Detection is not consent.

LM Studio is unauthenticated and bound to localhost by default; the owner must
deliberately choose **Serve on Local Network**. Even then, a detected-but-silent
system is **unaligned space**, not a member. The Federation may chart it, but it
forms no charter and extends no membership.

> **Detected ≠ member.** The Federation enters only where invited, and admits
> only worlds that have petitioned to join.

## 3. The petition — `vampire<NN>`

A world petitions for membership by setting its LM Studio API token to a
**recognised charter clause**. The clause is both the petition *and* the terms of
membership — it declares how much of the world's capacity may be drawn while it
is otherwise quiet:

| Charter clause | Terms of membership |
| --- | --- |
| *(no token set)* | **Unaligned.** May be charted if exposed, but no charter and no dividend. |
| `vampire` | **Open accord.** Up to full capacity while the owner is away. |
| `vampire50` | Up to **50%** capacity. |
| `vampire32` | Up to **32%** capacity. |
| `vampire8` | Up to **8%** capacity. |

Filing the petition is the act of formally requesting admission. It requires no
new technology and no change to LM Studio — the owner simply enters a recognised
value into a field that already exists. A generalised form `vampire<NN>` admits
any percentage while keeping the charter legible.

## 4. The clause is a public treaty, not an access code

A recognised charter clause is **published and well-known**. The consequence is
sharp: it cannot also be a secret. Anyone who knows the convention can read
`vampire50` and understand the terms.

So the clause is a **public treaty of intent**, not an access code:

- It declares *consent* and the *capacity ceiling*. Nothing more.
- It does **not** prove identity, and it does **not** repel intruders.

A world wanting both a private security code *and* a public tier can file a
two-part clause — `vampire32:<worldsecret>` — where the prefix is the public
treaty and the suffix is the genuine access code. Amending the prefix re-tiers;
amending the suffix re-keys.

## 5. Membership — what the world gains

An unaligned system is merely an isolated outpost. A world that petitions and is
admitted **joins the Federation**: it becomes part of something far larger and
shares in the benefits of the union.

- It gains access to coordinated operations — racing, fusion, failover, and
  load-balancing across many systems — capabilities no lone world possesses.
- It earns a **dividend** (the "pocket money" of the family-and-business
  scenario) for the idle capacity it contributes, metered against the terms it
  declared.

Membership is a *benefit extended in return for contribution*, never
requisition. The world is compensated for what it chose to give.

## 6. The charter is living — membership may be rescinded

Admission is not permanent. LM Studio tokens can be edited or deleted at any time,
so membership is a **console the owner commands**, not a treaty signed once:

- `vampire` → `vampire8` — *Our needs have grown.* Reduce the commitment.
- `vampire32` → *(no token)* — *We withdraw.* Membership is rescinded.
- *(no token)* → `vampire50` — *We petition to join.* Membership begins.

Persistent refusal (the owner deleting the token) is secession: the Federation
must read it as *"the world withdrew consent"* and remove it from the roster.

Because the charter can change mid-mission, the Federation owes three duties:

1. **Re-scan, never assume.** Poll the charter clause on the refresh cycle; the
   tier is live state, not an admission-time constant.
2. **The dividend is time-segmented.** If `vampire50` becomes `vampire8` at
   1500 hours, capacity contributed before 1500 is credited at 50% and after at
   8%. A mid-mission amendment is never retroactive.
3. **The ceiling binds operations in progress.** Lowering the tier throttles or
   stands down work already under way — the cap is a live ceiling, not merely a
   pledge about future missions.

## 7. The charter in one transmission

- **Many worlds, one Federation.** LM Studio is everywhere; the Federation is the
  thin layer that unites it.
- **Detected is not a member.** Charting a system is not consent.
- **The petition is the `vampire<NN>` clause** — request and terms in one,
  deployable on stock LM Studio.
- **The clause is a public treaty, not an access code.** It declares policy; it is
  not a secret. Identity, metering, and enforcement live in the Federation layer.
- **Membership is the reward** — coordination and dividend, extended for what is
  contributed.
- **The charter is living.** It may be re-tiered or rescinded at any time, and the
  Federation must honour every amendment immediately and segment the dividend
  honestly.
