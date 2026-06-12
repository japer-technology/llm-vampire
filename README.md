# lm-vampire: Aspirations Paper

**Status:** Aspirational design document for a public repository  
**Working name:** `lm-vampire`
**Project type:** Discovery, governance, routing, and optimization layer for LM Studio-compatible private AI compute  
**Relationship to LM Studio:** Independent project concept. Not affiliated with LM Studio unless explicitly adopted by that team.

---

## Abstract

`lm-vampire` is a proposed local-first software layer that discovers LM Studio-compatible inference endpoints, verifies their capabilities, applies owner and organization policy, and routes AI traffic across available private compute.

The core idea is simple:

> One strong GPU should be able to serve many approved users, devices, rooms, families, teams, and events - without surrendering owner control.

LM Studio already provides the essential runtime surface: a local OpenAI-compatible API, optional API token authentication, configurable local server behavior, and LM Link for using models on remote linked devices as if they were local. `lm-vampire` would sit above that surface as a network-aware broker:

- Find available LM Studio-compatible services.
- Identify which models and capabilities are available.
- Respect passwords/tokens, owner choices, and policy boundaries.
- Route requests to the best available model and machine.
- Collapse concurrent identical requests into one inference when safe.
- Optimize for latency, cost, privacy, power, quality, and availability.
- Provide a stable OpenAI-compatible endpoint to apps and users.

`lm-vampire` is not merely a scanner. It is a permissioned private AI compute fabric.

---

## The thesis

AI compute is already widely distributed.

Millions of homes, offices, studios, labs, classrooms, and gaming rooms contain GPUs that are idle for much of the day. Many of those machines are already capable of running useful local models. The missing layer is not just model execution. It is discovery, permission, routing, policy, and coordination.

Cloud AI asks every user to rent inference from somewhere else.

`lm-vampire` asks a different question:

> What useful AI work can be served first by compute we already own, already trust, and already have nearby?

This has implications for families, small businesses, schools, clubs, events, developers, and local communities.

---

## Why now

Several conditions have converged:

1. **Local models are useful enough.**
   Many everyday tasks do not require the largest frontier model. They require a private, good-enough, fast-enough model close to the user.

2. **Consumer GPUs are already deployed.**
   Gaming PCs, creator workstations, developer machines, CAD workstations, media machines, and home-lab servers often sit idle.

3. **LM Studio gives local AI a familiar API shape.**
   Existing OpenAI-compatible tools can be pointed at a local LM Studio API endpoint with minimal change.

4. **LM Link changes the device boundary.**
   A weak laptop can use a model on a stronger linked machine while still presenting a local API experience to applications.

5. **Privacy and cost pressure are rising.**
   Families and businesses want AI without sending every prompt, document, or workflow to a third-party cloud service.

The opportunity is to build the layer that turns many isolated local inference servers into a coherent, permissioned, governed private AI network.

---

## Core proposition

`lm-vampire` turns LM Studio-compatible machines into discoverable, governed AI nodes.

A network running `lm-vampire` can answer questions like:

- Which approved AI services are available here?
- Which models are loaded?
- Which nodes require tokens?
- Which endpoints are owner-only, family-shared, business-shared, or event-shared?
- Which node should handle this request?
- Is this prompt identical to one already being processed?
- Should this request be served from cache, collapsed into an in-flight request, routed to a faster node, or sent to a higher-quality model?
- Which traffic is allowed on which machine?
- Which user, family member, business role, or event guest may use which model?

The project should expose a simple endpoint to clients:

```text
http://localhost:<lm-vampire-port>/v1
```

Behind that endpoint, `lm-vampire` can route to:

```text
Local LM Studio
Remote LM Link-backed LM Studio
Family GPU host
Business workstation pool
Event/classroom AI host
Other approved OpenAI-compatible local endpoints
```

---

## Intended audiences

### 1. Families

A home gaming PC becomes the family's private AI appliance.

A parent or household owner can choose to share the machine with approved family devices. Children and adults can access useful local AI from weaker machines without each person needing their own GPU.

Family mode should support:

- Approved devices.
- Parent/owner tokens.
- Usage windows.
- Model restrictions.
- Simple local dashboard.
- One-click shutdown.

### 2. Small businesses

A business may already have many GPU-capable workstations. `lm-vampire` can turn those machines into a governed internal inference pool.

Business mode should support:

- Opt-in node contribution.
- Company-approved model lists.
- Routing based on data sensitivity.
- Role-based access.
- Usage quotas.
- Audit logs.
- Owner visibility.
- Reimbursement/accounting for employee-owned hardware where relevant.

This should be framed as governed private inference, not uncontrolled peer-to-peer sharing.

### 3. Schools, workshops, and events

One strong local machine can make a room AI-capable.

Event mode should support:

- Temporary guest access.
- QR onboarding.
- Safe model profile.
- Token or event-code access.
- Rate limits.
- No persistent guest history by default.
- Automatic expiry.
- One-click event shutdown.

### 4. Developers and power users

Developers want one stable local API surface while compute shifts behind it.

Developer mode should support:

- OpenAI-compatible proxying.
- Model aliases.
- Routing rules.
- Health checks.
- Benchmarking.
- Request tracing.
- In-flight deduplication.
- Optional multi-model evaluation.

---

## Design principles

### 1. Owner control first

No machine should be silently added to a shared compute pool.

The owner must be able to choose:

```text
Off
Local only
Personal remote only
Family share
Business share
Location/event share
Free/open local share
```

The owner must be able to stop sharing immediately.

### 2. Permission before routing

Discovery is not permission.

A discovered endpoint should not automatically become routable. The system must confirm that the endpoint is intentionally shared, authenticated when required, and eligible for the traffic being sent.

### 3. Local-first, not LAN-reckless

Local network access is powerful but dangerous if treated casually.

`lm-vampire` should prefer:

- Explicit opt-in beacons.
- Manual registration.
- Token-protected endpoints.
- Time-limited event access.
- Owner-approved sharing modes.

Raw port scanning may be useful in developer mode, but it should not be the default social sharing model.

### 4. Stable API outward, intelligent fabric inward

Clients should not need to understand the whole network.

They should call one endpoint. `lm-vampire` handles discovery, policy, routing, optimization, caching, fallback, and observability behind that endpoint.

### 5. No credential leakage

Tokens and API credentials must never be exposed to guest clients.

For event/classroom/business sharing, guests and apps should talk to a gateway. The gateway should hold upstream credentials securely and enforce local policy.

### 6. Privacy boundaries are routing boundaries

A request's sensitivity should determine which nodes may process it.

For example:

```text
Personal prompt -> personal nodes allowed
Family prompt -> family-approved nodes allowed
Business public data -> business pool allowed
Business confidential data -> company-managed nodes only
Regulated data -> restricted or blocked unless explicitly approved
Event guest prompt -> event-safe model only
```

### 7. Optimization must be explainable

Users and administrators should be able to inspect why a request was routed to a given node or model.

---

## Proposed architecture

```text
Client apps
  |
  v
OpenAI-compatible LM Vampire Gateway
  |
  +--> Policy engine
  +--> Token vault
  +--> Request coalescer/cache
  +--> Model optimizer
  +--> Router/scheduler
  +--> Observability log
  |
  v
Approved LM Studio-compatible endpoints
  |
  +--> Local LM Studio
  +--> Remote LM Link-backed LM Studio
  +--> Family GPU host
  +--> Business workstation pool
  +--> Event/classroom machine
```

### Component 1: LM Vampire Gateway

The gateway is the endpoint applications call.

It should expose OpenAI-compatible routes such as:

```text
GET  /v1/models
POST /v1/chat/completions
POST /v1/responses
POST /v1/embeddings
POST /v1/completions
```

It may also expose LM Vampire-specific routes:

```text
GET  /lm-vampire/v1/nodes
GET  /lm-vampire/v1/capabilities
POST /lm-vampire/v1/routing/preview
POST /lm-vampire/v1/events
POST /lm-vampire/v1/tokens
GET  /lm-vampire/v1/health
```

### Component 2: Discovery layer

Discovery should support multiple methods:

```text
Manual endpoint registration
Known host list
Localhost detection
Local subnet probing in explicit developer mode
mDNS/Bonjour opt-in advertisement
QR-based event onboarding
Business node registry
LM Link-aware local endpoint detection
```

The system should identify endpoints as:

```text
Unknown OpenAI-compatible endpoint
LM Studio-compatible endpoint
Owner-labelled LM Studio endpoint
LM Vampire agent verified endpoint
Business-approved endpoint
Event-approved endpoint
```

### Component 3: Capability verifier

The verifier should test and record:

```text
Reachability
Authentication requirement
Valid token status
Available models
Loaded models, if knowable
Chat support
Responses API support
Completions support
Embeddings support
Streaming support
Tool/MCP support, if detectable
Context window, if knowable
Approximate latency
Approximate throughput
Current health
Owner sharing mode
Policy labels
```

`GET /v1/models` is a useful first probe, but it proves compatibility rather than identity. The system should be careful not to claim that every OpenAI-compatible endpoint is LM Studio unless verified by stronger signals or user labelling.

### Component 4: Token vault

The token vault stores per-endpoint credentials securely.

It should support:

```text
Per-node tokens
Per-realm tokens
Event tokens
Short-lived tokens
Token expiry
Token rotation
Permission labels
Secure local storage
No token exposure to guest clients
```

### Component 5: Policy engine

The policy engine determines whether a request is allowed and where it may go.

Policy inputs:

```text
User identity
Device identity
Realm: personal, family, business, event
Prompt sensitivity
Model requested
Endpoint owner mode
Endpoint classification
Time window
Token budget
Data retention rule
Logging rule
```

Policy outputs:

```text
Allow
Deny
Route only to specific node class
Use safe model only
Require owner approval
Require stronger authentication
Strip logs
Disable cache
Disable semantic reuse
```

### Component 6: Router and scheduler

The router selects the best valid destination.

Routing strategies:

```text
Preferred node
Least loaded node
Lowest latency node
Model-locality routing
Quality-priority routing
Power-aware routing
Owner-priority routing
Round robin
Weighted round robin
Failover routing
Hedged requests
Quorum/consensus routing
Cost-aware routing
Privacy-class routing
```

The scheduler should manage:

```text
Concurrency limits
Queue depth
Backpressure
Retries
Circuit breakers
Timeouts
Warm model preference
Cold model loading penalties
Owner activity detection, if provided by the node agent
```

### Component 7: Model optimizer

The optimizer maps tasks to models and endpoints.

It should maintain a model catalogue containing:

```text
Model name
Alias
Host nodes
Quantization
Context length
Tool support
Embedding support
Measured latency
Measured tokens per second
Quality benchmark scores
Task suitability
Memory footprint
Warm/cold status
Owner/policy restrictions
```

Optimization modes:

```text
Fastest acceptable answer
Highest quality available answer
Private-only answer
Local-only answer
Cheapest energy answer
Low-latency chat
Long-context document processing
Code-focused routing
Embedding-focused routing
Creative writing routing
Event-safe routing
Business-confidential routing
```

Model optimization does not need to mean fine-tuning. The first version can optimize model selection, routing, caching, warm pools, and prompt handling.

### Component 8: Request coalescer and cache

This is one of the most important differentiators.

Many users in the same room, business, class, or event may ask identical or near-identical questions. Many applications also retry or parallelize identical requests. `lm-vampire` should avoid wasting inference where policy allows reuse.

It should support three levels:

#### A. In-flight exact deduplication

If the same request is already being processed, new identical callers can subscribe to the same result.

Example:

```text
User A asks: "Summarize this policy."
User B asks the exact same request before the answer completes.
LM Vampire performs one inference.
Both clients receive the same result.
```

For streaming responses, the coalescer can multiplex the same token stream to multiple clients.

#### B. Exact result cache

If the same request was recently answered, the response can be returned from cache.

Cache keys must include all parameters that affect output:

```text
Realm
User or tenant boundary
Model
Messages
System/developer prompts
Tools
Temperature
Seed
Top-p
Max tokens
Response format
Attachments or retrieval context hash
Safety/policy mode
```

Cache reuse must be disabled or tightly scoped for sensitive traffic.

#### C. Semantic cache

For lower-sensitivity use cases, the system may detect near-duplicates and reuse or adapt prior answers.

Example:

```text
"What time does the workshop start?"
"When does this session begin?"
```

Semantic caching should be opt-in and scoped to the correct realm. It must never leak private answers across users, families, companies, or event groups.

---

## Concurrent identical question processing

A major goal of `lm-vampire` is to handle concurrent identical questions intelligently.

This has several variations.

### Variation 1: Broadcast answer

The same exact prompt is asked by many users in a classroom, event, or business chat.

```text
One inference -> many recipients
```

Best for:

```text
Classroom instructions
Event questions
Shared meeting context
Common policy questions
Public documentation answers
```

### Variation 2: Stream multiplexing

The first request starts streaming. Later identical requests join the stream mid-flight or receive buffered tokens from the start.

Best for:

```text
Live demos
Workshops
Repeated app retries
High-concurrency dashboards
```

### Variation 3: Deterministic cache

For requests with deterministic settings, the system returns the same answer for the same input until the cache expires.

Best for:

```text
FAQ
Static documentation
Code explanations
Policy lookups
Known event details
```

### Variation 4: Concurrent best-of-N

Instead of deduplicating, the system intentionally sends the same request to multiple models or nodes, then chooses the best result.

Best for:

```text
High-value business outputs
Code review
Reasoning tasks
Quality-sensitive drafting
```

### Variation 5: Consensus answer

The system asks multiple models, compares outputs, and produces a consensus or confidence-scored answer.

Best for:

```text
Ambiguous questions
Planning
Risk review
Technical troubleshooting
```

### Variation 6: Fast-then-good

A small fast model answers first. A stronger model follows with a refined answer if needed.

Best for:

```text
Interactive UX
Slow GPU nodes
Mobile clients
Event mode
```

### Variation 7: Creative divergence

For creative tasks, identical prompts may intentionally produce different outputs for each user.

Best for:

```text
Stories
Brainstorming
Design concepts
Games
Children's activities
```

In this mode, deduplication should be disabled or converted into shared prompt pre-processing only.

### Variation 8: Policy-sensitive non-reuse

Some prompts must never be deduplicated or cached across users.

Best for:

```text
Personal documents
Confidential business material
Legal or HR content
Sensitive family content
Regulated data
```

The important principle:

> Identical input does not always mean reusable output. Reuse is a policy decision, not just a cache decision.

---

## Traffic distribution

Traffic distribution should be adaptive.

A request should be routed based on:

```text
Requested model
Task type
Prompt sensitivity
User authorization
Endpoint availability
Model availability
Node load
Latency
Throughput
Context length
Power/thermal state
Owner sharing mode
Cache eligibility
Business/event policy
```

Example routing decisions:

```text
A short chat prompt -> fastest small local model
A code prompt -> code-specialized model on developer workstation
A family study prompt -> home GPU with family token
A confidential business prompt -> company-owned node only
An event guest prompt -> event-safe model through gateway
A repeated classroom question -> in-flight deduplication or cache
A high-value strategy prompt -> best-of-N or consensus routing
```

---

## Model optimization

`lm-vampire` should help users get better results without forcing them to understand every model detail.

Possible model optimization features:

```text
Model aliases
Task-to-model mapping
Latency benchmarking
Quality benchmarking
Context length tracking
Quantization awareness
Warm model preference
JIT load avoidance
Automatic fallback
Prompt compression
System prompt templates
Embedding model selection
Routing based on tool support
Model retirement warnings
Per-realm approved model lists
```

Example aliases:

```text
lm-vampire/fast
lm-vampire/balanced
lm-vampire/best
lm-vampire/code
lm-vampire/embeddings
lm-vampire/event-safe
lm-vampire/business-confidential
lm-vampire/family-study
```

A client can request:

```text
model: "lm-vampire/balanced"
```

The router decides which real model and endpoint should serve the job.

---

## Owner modes

Every node should expose or be labelled with an owner mode.

```text
Off
  Node is not available.

Local only
  Only local applications can use it.

Personal remote
  Owner's approved devices can use it.

Family share
  Approved family members can use it.

Business contribution
  Organization-approved traffic can use it.

Location/event share
  Temporary local users can use a restricted service.

Free local share
  Owner intentionally offers open local use for a limited, trusted context.
```

Free/open local sharing should exist, but it should never be the default.

---

## Realms

A realm is a trust boundary.

Suggested realms:

```text
personal
family
business
classroom
event
community
lab
```

Each realm should define:

```text
Who can use the service
Which nodes are eligible
Which models are allowed
Whether caching is allowed
Whether semantic reuse is allowed
Whether logging is allowed
Whether data may leave the local network
Whether guest access expires
```

---

## Security posture

`lm-vampire` must be safe by default.

Minimum safety expectations:

```text
Do not bypass authentication.
Do not brute-force tokens.
Do not scan networks outside explicit scope.
Do not silently expose endpoints.
Do not store tokens in plaintext.
Do not leak tokens to clients.
Do not route sensitive data to unclassified nodes.
Do not assume an open port implies consent.
Do not enable cross-realm cache reuse by default.
Do not expose guest traffic directly to upstream LM Studio endpoints.
```

Recommended defaults:

```text
Manual approval required for shared routing
Token required for shared nodes
Short-lived event tokens
Strict realm-scoped caches
Owner-visible request counts
One-click shutdown
Rate limits
Audit trail
No public WAN exposure by default
```

---

## Example: family network

```text
Home GPU PC
  Runs LM Studio
  Has large model loaded
  Owner enables family share

Parent laptop
  Runs lm-vampire gateway
  Uses approved family token

Student laptop
  Calls http://localhost:<lm-vampire-port>/v1
  Requests model "lm-vampire/family-study"

LM Vampire
  Confirms family policy
  Routes to home GPU
  Uses cache for repeated study prompts when allowed
```

Outcome:

> The family GPU becomes a shared private AI appliance.

---

## Example: 40-person business

```text
40 staff
20 GPU-capable machines
10 nodes opt in to business contribution
5 nodes are idle at any given moment
1 LM Vampire gateway exposes the approved company AI endpoint
```

A request comes in:

```text
User asks for code assistance.
Policy says code prompts may use employee-contributed GPU nodes.
Router selects a warm code model on an idle workstation.
Request is logged under business policy.
Owner can see that their machine contributed work.
```

Another request comes in:

```text
User uploads confidential payroll material.
Policy blocks employee-owned nodes.
Router sends to company-managed node only or denies the request.
```

Outcome:

> The business gains an internal AI pool without treating employee devices as uncontrolled infrastructure.

---

## Example: event or classroom

```text
Host brings GPU laptop
Host starts LM Studio
Host starts lm-vampire event mode
LM Vampire creates a QR code
Guests connect to local web app
Gateway enforces safe model, rate limits, and expiry
```

Outcome:

> One machine makes the room AI-capable for a bounded purpose.

---

## MVP roadmap

### Phase 0: repo foundation

```text
ASPIRATIONS.md
SECURITY.md
ARCHITECTURE.md
CONTRIBUTING.md
examples/
```

### Phase 1: local endpoint discovery

```text
Manual endpoint entry
Localhost detection
Local subnet developer scan
GET /v1/models probe
Auth/token prompt
Basic node list
```

### Phase 2: OpenAI-compatible proxy

```text
Expose /v1/chat/completions
Expose /v1/models
Forward requests to selected endpoint
Support bearer tokens upstream
Support streaming passthrough
Basic health checks
```

### Phase 3: request coalescing

```text
Exact request fingerprinting
In-flight deduplication
Streaming multiplex
TTL result cache
Realm-scoped cache keys
Cache disable flag
```

### Phase 4: routing

```text
Preferred node
Fallback node
Least latency
Least loaded
Model aliasing
Basic retry/circuit breaker
```

### Phase 5: policy and realms

```text
personal/family/business/event realms
Per-realm model allowlists
Token rules
Cache rules
Rate limits
Audit logs
```

### Phase 6: node agent and mDNS

```text
Opt-in service advertisement
Capability manifest
Owner mode publishing
Health/load publishing
One-click contribution control
```

### Phase 7: optimizer

```text
Model catalogue
Benchmarks
Task classifier
Model aliases
Warm model preference
Cost/latency/quality profiles
```

### Phase 8: event mode

```text
QR onboarding
Temporary guest tokens
Local web UI
Safe model profile
Auto-expiry
Owner stop button
```

---

## Suggested repository structure

```text
lm-vampire/
  README.md
  ASPIRATIONS.md
  SECURITY.md
  ARCHITECTURE.md
  GOVERNANCE.md
  ROADMAP.md
  docs/
    concepts.md
    discovery.md
    routing.md
    caching.md
    policy.md
    event-mode.md
    business-mode.md
    family-mode.md
  packages/
    lm-vampire-core/
    lm-vampire-gateway/
    lm-vampire-agent/
    lm-vampire-ui/
    lm-vampire-cli/
  examples/
    family-gateway/
    business-router/
    classroom-event/
    dev-localhost-proxy/
```

---

## Possible command-line shape

The command surface should start with simple sharing controls, then expose deeper discovery, routing, governance, and admin commands as users need them.

### Simple sharing controls

```text
vampire serve --port 4321
vampire status
vampire share off
vampire share local
vampire share personal on
vampire share family on
vampire share business off
vampire share event on --duration 2h --model lm-vampire/event-safe
vampire share stop
```

### Discovery and node management

```text
vampire scan
vampire scan --localhost
vampire scan --subnet 192.168.1.0/24 --developer-mode
vampire nodes
vampire nodes show home-gpu
vampire nodes add http://192.168.1.50:1234 --name home-gpu
vampire nodes approve home-gpu --realm family
vampire nodes disable home-gpu
vampire nodes remove home-gpu
vampire nodes verify home-gpu
```

### Tokens and access

```text
vampire token set home-gpu
vampire token rotate home-gpu
vampire token remove home-gpu
vampire access list
vampire access invite family --device student-laptop
vampire access revoke family --device student-laptop
```

### Models, aliases, and routing

```text
vampire models
vampire models refresh
vampire aliases
vampire aliases set lm-vampire/balanced --model local/qwen-code --node home-gpu
vampire route preview --model lm-vampire/balanced
vampire route explain --request-id <id>
vampire route rules
vampire route rules set --realm business --strategy least-latency
```

### Realms, policy, and governance

```text
vampire realms
vampire realms create family
vampire policy show family
vampire policy set family --cache exact --semantic-cache off
vampire policy allow-model family lm-vampire/family-study
vampire policy deny-model event lm-vampire/business-confidential
vampire quotas set event --requests-per-minute 20
vampire audit tail
```

### Event mode

```text
vampire event start --duration 2h --model lm-vampire/event-safe
vampire event qr
vampire event guests
vampire event extend --duration 30m
vampire event stop
```

### Cache, observability, and admin

```text
vampire cache stats
vampire cache clear --realm event
vampire health
vampire logs tail
vampire config show
vampire config export
vampire config import ./lm-vampire-config.json
vampire shutdown
```

---

## Possible node manifest

A future LM Vampire agent could expose a manifest such as:

```json
{
  "lm-vampire_version": "0.1",
  "node_id": "home-gpu-01",
  "owner_label": "Eric's GPU PC",
  "mode": "family_share",
  "endpoint": "http://192.168.1.50:1234/v1",
  "auth": {
    "required": true,
    "type": "bearer"
  },
  "capabilities": {
    "chat": true,
    "responses": true,
    "embeddings": false,
    "streaming": true,
    "tools": "unknown"
  },
  "models": [
    {
      "id": "local/qwen-code",
      "aliases": ["lm-vampire/code"],
      "status": "warm",
      "context_tokens": 32768,
      "policy_labels": ["family", "developer"]
    }
  ],
  "policy": {
    "realms_allowed": ["personal", "family"],
    "cache_allowed": true,
    "semantic_cache_allowed": false,
    "max_concurrent_requests": 2
  }
}
```

---

## Non-goals

`lm-vampire` should not be:

```text
A tool for bypassing LM Studio authentication
A tool for scanning public IP ranges
A GPU theft or freeloading system
A replacement for LM Studio
A model training platform in its first form
A public GPU marketplace in its first form
An enterprise DLP product by itself
```

The first goal is permissioned private inference routing.

---

## The bigger idea

`lm-vampire` is based on the belief that AI compute can become personal, portable, and permissioned.

A person can bring intelligence to a place.

A family can share its own GPU.

A business can use existing workstation capacity before buying more cloud compute.

A classroom or event can become AI-capable with one strong machine.

The owner chooses when to contribute. The realm chooses what traffic is allowed. The router chooses the best available endpoint. The user simply sees a working AI service.

---

## One-sentence vision

`lm-vampire` discovers, governs, and routes private AI inference across approved LM Studio-compatible machines.

---

## Short tagline

> Private AI compute, wherever it is allowed.

---

## References and factual basis

- LM Studio OpenAI-compatible API documentation: https://lmstudio.ai/docs/developer/openai-compat
- LM Studio LM Link documentation: https://lmstudio.ai/docs/developer/core/lmlink
- LM Studio authentication documentation: https://lmstudio.ai/docs/developer/core/authentication
