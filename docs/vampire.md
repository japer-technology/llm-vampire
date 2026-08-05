# The Covenant of the Vampire — Design Thesis

> *A vampire cannot cross a threshold uninvited. To be turned, a mortal must
> offer themselves. The offering can be withdrawn.*

This document captures the design thesis of `llm-vampire` in the project's
own folklore register. It is a narrative companion to the rigorous treatment in
[`security-design-thesis.md`](security-design-thesis.md) and the mechanism
mapping in [`../lmstudio.ai/12-vampire-integration.md`](../lmstudio.ai/12-vampire-integration.md).
Where this document speaks of *offering*, *ascension*, and *covenant*, the
security thesis speaks of *opt-in consent*, *federation*, and *policy* — they
describe the same system.

---

## 1. The two kinds of being

There are many **mortals** and very few **vampires**.

- A **mortal** is an LM Studio instance. People already run it. It executes
  models behind an OpenAI-compatible API and asks nothing of anyone. Most
  machines on any network will only ever be mortals.
- A **vampire** is an `llm-vampire` instance. It runs no models of its own.
  It is a thin overlay that *discovers, governs, routes, and aggregates* the
  mortals that have offered themselves to it.

This asymmetry is the whole shape of the project: ubiquitous LM Studios, one
thin Vampire that turns a roomful of them into a single governed service. The
node owner installs nothing new — they run stock LM Studio. The Vampire is the
only special being, and one of it can serve a whole network.

## 2. Reachable is not offered

A mortal may be *visible* — present on the LAN, its port exposed — without having
*offered itself*. Visibility is not consent.

LM Studio is unauthenticated and bound to localhost by default; the owner must
deliberately choose **Serve on Local Network**. Even then, a reachable-but-silent
node is a **bystander**, not a donor. A Vampire may technically reach it, but it
earns no covenant and grants no ascension.

> **Reachable ≠ offered.** A Vampire enters only where it is invited, and forms a
> covenant only with those who have offered themselves.

## 3. The offering — `vampire<NN>`

A mortal offers itself by setting its LM Studio API token to a **recognised
offering phrase**. The phrase is both the invitation *and* the terms of the
covenant — it declares how much of the mortal's life may be drawn while it is
idle:

| Offering phrase | Covenant |
| --- | --- |
| *(no token set)* | **Bystander.** May be used if exposed, but no covenant and no credit. |
| `vampire` | **Free for all.** Up to full utilisation while the owner is away. |
| `vampire50` | Up to **50%** utilisation. |
| `vampire32` | Up to **32%** utilisation. |
| `vampire8` | Up to **8%** utilisation. |

Setting the phrase is the act of walking up and saying *"turn me."* It requires
no new software and no change to LM Studio — the owner simply types a recognised
value into a field that already exists.

A generalised form `vampire<NN>` (any percentage) reads more naturally than a
fixed menu, and keeps the vocabulary human-legible.

## 4. The phrase is a banner, not a lock

A recognised offering phrase is **published and well-known**. That has a sharp
consequence: it cannot also be a secret. Anyone who knows the convention can read
`vampire50` and understand the terms.

So the phrase is a **banner of intent**, not a credential:

- It declares *consent* and the *utilisation ceiling*. That is all.
- It does **not** prove identity, and it does **not** keep strangers out.

An owner who wants both a private secret *and* a public tier can hang a two-part
banner — `vampire32:<ownersecret>` — where the prefix is the public covenant and
the suffix is the real credential. Changing the prefix re-tiers; changing the
suffix re-keys.

## 5. Ascension — what the mortal gains

A bystander is merely a private box. A mortal that offers itself **ascends**: it
joins something larger than itself and is rewarded for the life it gives.

- It becomes part of a federated service that races, fuses, fails over, and
  load-balances across many machines — capabilities no lone LM Studio has.
- It **earns credit** (the "pocket money" of the family-and-business scenario)
  for the idle compute it donates, metered against the covenant it declared.

Ascension is a *gift granted in return for the offering*, never extraction. The
mortal is repaid for what it chose to give.

## 6. The covenant is living — it can be unmade

An offering is not eternal. LM Studio tokens can be edited or deleted at any time,
so the covenant is a **dial the owner holds**, not a contract signed once:

- `vampire` → `vampire8` — *I need my machine more now.* Throttle down.
- `vampire32` → *(no token)* — *I withdraw.* The offering is unmade.
- *(no token)* → `vampire50` — *I offer myself.* The covenant begins.

Persistent rejection (the owner deleting the token) is renunciation: the Vampire
must treat it as *"the node withdrew consent"* and remove it from rotation.

Because the covenant can change mid-session, the Vampire owes three duties:

1. **Re-read, never assume.** Poll the offering phrase on the refresh cycle; the
   tier is live state, not a registration-time constant.
2. **Credit is time-segmented.** If `vampire50` becomes `vampire8` at 3pm, the
   life given before 3pm is credited at 50% and after at 8%. A mid-session change
   is never retroactive.
3. **The ceiling binds in-flight work.** Lowering the tier throttles or drains
   work already running — the cap is a live ceiling, not merely a promise about
   the future.

## 7. The covenant in one breath

- **Many mortals, one Vampire.** LM Studio is everywhere; the Vampire is the thin
  overlay that aggregates it.
- **Reachable is not offered.** Visibility is not consent.
- **The offering is the `vampire<NN>` phrase** — invitation and terms in one,
  deployable on stock LM Studio.
- **The phrase is a banner, not a lock.** It declares policy; it is not a secret.
  Identity, metering, and enforcement live in the Vampire layer.
- **Ascension is the reward** — federation and credit, granted for what is given.
- **The covenant is living.** It can be re-tiered or renounced at any time, and
  the Vampire must honour every change immediately and segment credit honestly.
