# The Maths of LM Studio Vampire

This document describes the mathematics behind the `lmstudio-vampire` mechanism:
a gateway that aggregates owner-approved LM Studio endpoints into one governed,
OpenAI-compatible service, and routes, coalesces, caches, races, and fuses
requests across them.

It complements [DESIGN-API.md](DESIGN-API.md) (especially §8 modes, §9 routing
strategies, §10 fusion strategies, and §18 metrics) by making the underlying
quantitative models explicit.

---

## 1. The system as a formal model

Let the fleet at time *t* be a set of nodes:

```
N(t) = { n₁, n₂, …, n_k }
```

Each node `nᵢ` carries a state vector derived from the node agent / metrics API
(DESIGN-API.md §4.1, §18):

```
sᵢ = ( Lᵢ, Tᵢ, Qᵢ, Cᵢ, Uᵢ, Aᵢ )
```

where

| Symbol | Meaning                              | Source field            |
|--------|--------------------------------------|-------------------------|
| `Lᵢ`   | network/inference latency (ms)       | `latency_ms`            |
| `Tᵢ`   | throughput (tokens per second)       | `tokens_per_second`     |
| `Qᵢ`   | queue depth (requests waiting)       | `queue_depth`           |
| `Cᵢ`   | context window (tokens)              | `context_length`        |
| `Uᵢ`   | utilisation (CPU/GPU/memory percent) | `cpu_percent`, `gpu_percent`, `memory_percent` |
| `Aᵢ`   | availability indicator ∈ {0, 1}      | `status == "online"`    |

Each virtual model `vampire:x` maps to a candidate set
`M(x) ⊆ N(t)` — the nodes that host a compatible physical model. Routing is the
problem of choosing, for each request `r`, a node:

```
route(r) = argmax over nᵢ ∈ M(x), Aᵢ = 1 of  score(nᵢ, r)
```

Every routing strategy in §9 of the design is a particular choice of `score`.

---

## 2. Routing strategies as scoring functions

### 2.1 Round robin (modular arithmetic)

With candidate nodes indexed `0 … k−1` and a monotone request counter `c`:

```
route(r_c) = n_(c mod k)
```

Each node receives a `1/k` share of traffic. **Weighted round robin** assigns
integer weights `wᵢ` and cycles through a schedule of length `W = Σ wᵢ`, giving
node `i` a long-run traffic share of exactly `wᵢ / W`.

### 2.2 Least busy / least latency / highest throughput (argmin/argmax)

These are single-criterion selections:

```
least_busy:                route(r) = argmin Qᵢ
least_latency:             route(r) = argmin Lᵢ
highest_tokens_per_second: route(r) = argmax Tᵢ
```

Ties are broken by round robin to avoid herd behaviour (all traffic piling onto
one momentarily-idle node).

### 2.3 `best_available` (weighted multi-criteria score)

The design's `best_available` strategy takes explicit weights
(DESIGN-API.md §9):

```json
"weights": {
  "latency": 0.25,
  "tokens_per_second": 0.25,
  "queue_depth": 0.25,
  "quality_score": 0.25
}
```

Because the criteria have different units and directions ("lower is better"
vs. "higher is better"), each metric is first normalised to `[0, 1]` across the
candidate set. For a higher-is-better metric `m`:

```
m̂ᵢ = (mᵢ − min m) / (max m − min m)
```

and for lower-is-better metrics (latency, queue depth) the complement
`1 − m̂ᵢ` is used. The node score is then a convex combination:

```
score(nᵢ) = w_L·(1 − L̂ᵢ) + w_T·T̂ᵢ + w_Q·(1 − Q̂ᵢ) + w_q·q̂ᵢ ,   Σ w = 1
```

and the router picks `argmax score(nᵢ)`. With all weights equal to `0.25` this
is the unweighted average of the four normalised criteria. `quality_score` and
`cost_score` strategies are the degenerate cases where one weight is 1 and the
rest are 0.

### 2.4 Smoothed measurements (EWMA)

Raw latency and throughput samples are noisy. The router maintains
exponentially weighted moving averages so a single slow sample does not
permanently penalise a node:

```
L̄ᵢ ← α · L_sample + (1 − α) · L̄ᵢ ,    0 < α ≤ 1
```

Smaller `α` means more smoothing (longer memory); the effective averaging
window is roughly `1/α` samples.

### 2.5 Constraint strategies (feasibility filters)

`context_window`, `trusted_only`, `privacy_policy`, and `power_saver` are not
scores but **hard constraints** that shrink the feasible set before scoring:

```
M'(x) = { nᵢ ∈ M(x) : Cᵢ ≥ tokens(r),  trusted(nᵢ),  policy(nᵢ, r) = allow }
```

Routing then proceeds over `M'(x)`. If `M'(x) = ∅`, the request fails fast (or
falls through a `fallback_chain`, §2.6).

### 2.6 Fallback chains (first success over an ordered sequence)

A `fallback_chain` is an ordered list `(n₁, n₂, …, n_k)`; the result is the
first attempt that succeeds. If each attempt fails independently with
probability `fᵢ`, the chain's overall failure probability is the product:

```
P(chain fails) = ∏ᵢ fᵢ
```

With `k` nodes each failing 10% of the time, the chain fails only
`0.1^k` of the time — three nodes already give 99.9% effective availability.
The expected number of attempts is `1 + f₁ + f₁f₂ + …`.

---

## 3. Queueing: why load-aware routing wins

Each node behaves approximately like a single-server queue (an LM Studio
instance processes generations one at a time). Using the M/M/1 approximation
with arrival rate `λᵢ` and service rate `μᵢ` (requests/sec, where
`μᵢ ≈ Tᵢ / E[output tokens]`):

```
ρᵢ = λᵢ / μᵢ                      (utilisation, must stay < 1)
E[waiting + service] = 1 / (μᵢ − λᵢ)
E[queue length]      = ρᵢ / (1 − ρᵢ)
```

Two consequences drive the design:

1. **Latency explodes near saturation.** As `ρ → 1`, expected latency
   `1/(μ−λ) → ∞`. This is why `least_busy` uses queue depth `Qᵢ` — it is a
   direct, real-time estimate of `ρᵢ/(1−ρᵢ)` and reacts before latency
   measurements do.
2. **Pooling beats partitioning.** Aggregating `k` nodes behind one gateway
   approximates an M/M/k system, whose expected wait is strictly lower than
   `k` independent M/M/1 queues at the same total load, because a request
   never waits while *any* server is idle. This is the quantitative case for
   the gateway existing at all.

---

## 4. Coalescing and caching

### 4.1 Request identity (hashing)

Coalescing and exact-result caching require a canonical request key. The
request body (model, messages, sampling parameters) is serialised
canonically and hashed:

```
key(r) = SHA-256( canonical(r) )
```

SHA-256 gives a collision probability of roughly `q² / 2²⁵⁷` for `q` distinct
requests (birthday bound) — negligible for any realistic workload, so two
requests share a key if and only if they are identical. (The design already
uses `sha256` hashes for model/response attestation, DESIGN-API.md §19.)

Note: coalescing identical prompts into one inference is only semantically
safe for deterministic decoding (`temperature = 0` or a fixed `seed`);
otherwise identical prompts legitimately yield different samples.

### 4.2 Coalescing factor

If `d` identical requests arrive while one inference for that key is in
flight, all `d` are attached to the single upstream call. The backend load
reduction for that key is a factor of `d`; system-wide, if a fraction `p` of
arrivals are coalesced duplicates, backend traffic shrinks to `(1 − p)` of
client traffic.

### 4.3 Cache hit rate and effective latency

With cache hit probability `h`, cache lookup latency `L_c`, and inference
latency `L_b`:

```
E[latency]      = h · L_c + (1 − h) · L_b
backend load    = (1 − h) · λ
```

Since `L_c ≪ L_b` (microseconds vs. seconds), even modest hit rates yield
large mean-latency reductions. TTL-bounded entries trade staleness `≤ TTL`
for these gains.

---

## 5. Race mode (order statistics)

`race` mode (DESIGN-API.md §8.2) sends one request to `k` nodes and returns
the first completion, cancelling the rest. The winning latency is the
**minimum order statistic**:

```
L_race = min(L₁, L₂, …, L_k)
```

For independent latencies, the distribution function is

```
P(L_race ≤ t) = 1 − ∏ᵢ (1 − Fᵢ(t))
```

For i.i.d. exponential latencies with rate `μ`, `E[L_race] = 1/(kμ)` — racing
`k` nodes divides expected latency by `k`. The practical benefit is even
larger in the *tail*: the p99 of the minimum is dramatically better than the
p99 of any single node, which is why racing is the classic cure for
tail-latency stragglers. The cost is up to `k×` compute (mitigated by
cancellation as soon as a winner emerges).

---

## 6. Fusion strategies (voting and aggregation)

Fusion (DESIGN-API.md §8.4, §10) runs `n` candidate models and combines their
answers.

### 6.1 Majority vote

Answers are bucketed by semantic equivalence; the winning bucket is

```
answer = argmax_a |{ i : answer_i ≡ a }|
```

with `min_agreement` (e.g. `2`) as a quorum threshold: if no bucket reaches
the quorum, fusion falls back to judge synthesis or returns all candidates.

**Why voting helps (Condorcet's jury theorem).** If each of `n` independent
models answers correctly with probability `p > 1/2`, the probability that a
majority is correct is

```
P(majority correct) = Σ_{j > n/2} C(n, j) · pʲ · (1 − p)^(n − j)
```

which is strictly greater than `p` and tends to 1 as `n → ∞`. Three models at
`p = 0.8` give a majority accuracy of `0.8³ + 3·0.8²·0.2 = 0.896`. The gain
relies on the *independence* of errors, which is exactly why fusion draws
candidates from **different** models/nodes (`vampire:general`,
`vampire:reasoning`, `vampire:critic`) rather than sampling one model thrice.

### 6.2 Best-of-n and ranked vote

`best_of_n` scores each candidate with a judge model and selects the argmax.
If the judge's scoring is even weakly correlated with true quality, the
expected quality of `max(X₁, …, X_n)` is non-decreasing in `n` (the maximum
order statistic), with diminishing returns — most of the gain comes from the
first few candidates. `ranked_vote` aggregates full preference orderings
(e.g. Borda count: candidate ranked `j`-th of `n` by a voter receives
`n − j` points; highest total wins).

### 6.3 Agreement thresholds

`consensus_only` and `min_agreement` are quorum rules: accept an answer only
if at least `q` of `n` candidates agree (`q/n > 1/2` for strict majority).
Raising `q` trades coverage (more "no consensus" outcomes) for precision
(fewer confidently-wrong outputs).

### 6.4 Cost of fusion

All fusion modes multiply compute: `n` candidate generations plus (for
judge-based strategies) one judge pass over the concatenated candidates.
Latency is dominated by the **slowest** candidate — the *maximum* order
statistic, `max(L₁, …, L_n)`, the mirror image of race mode — plus the judge
pass. Fusion therefore buys quality with both compute and latency, while race
buys latency with compute.

---

## 7. Aggregate capacity and availability

For the fleet as a whole:

```
Total throughput:   T_total = Σᵢ Aᵢ · Tᵢ           (tokens/sec)
Service capacity:   μ_total = Σᵢ Aᵢ · μᵢ           (requests/sec)
```

If node `i` is independently online with probability `aᵢ`, the probability
that at least one node can serve virtual model `x` is

```
P(x available) = 1 − ∏_{i ∈ M(x)} (1 − aᵢ)
```

Availability compounds geometrically: two nodes at 95% give 99.75%; three
give 99.99%. This is the same product law as the fallback chain (§2.6), and
it is the mathematical core of the project's premise — many individually
unreliable, idle machines combine into one service whose availability and
capacity exceed any single member.

---

## 8. Summary of the governing equations

| Mechanism        | Governing mathematics                                  |
|------------------|--------------------------------------------------------|
| Round robin      | `route(r_c) = n_(c mod k)`; share `wᵢ/Σw` when weighted |
| Best available   | `argmax Σ w_m · m̂` over normalised metrics, `Σ w = 1`  |
| Metric smoothing | EWMA: `x̄ ← α·x + (1−α)·x̄`                              |
| Load awareness   | M/M/1: `E[T] = 1/(μ−λ)`, blow-up as `ρ → 1`            |
| Pooling          | M/M/k wait < k × M/M/1 wait at equal load              |
| Coalescing/cache | `key = SHA-256(canonical(r))`; `E[L] = h·L_c + (1−h)·L_b` |
| Race             | `L = min(L₁…L_k)`; `E = 1/(kμ)` for i.i.d. exponential |
| Fallback/availability | `P(fail) = ∏ fᵢ` — failures multiply away         |
| Majority fusion  | Condorcet: `Σ_{j>n/2} C(n,j) pʲ(1−p)^{n−j} > p` for `p > ½` |
| Fleet capacity   | `T_total = Σ Aᵢ·Tᵢ`; `P(avail) = 1 − ∏(1 − aᵢ)`         |
