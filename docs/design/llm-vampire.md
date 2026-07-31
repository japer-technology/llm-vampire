# LLM Vampire Higher-Level Intelligence Specification

**Status:** Draft
**Version:** 0.1
**Product:** LLM Vampire
**Scope:** Model-independent orchestration, intelligence services, memory, verification, workflows and agents

---

## 1. Executive Summary

LLM Vampire is a provider-neutral control plane for language-model services available across a local or trusted network.

The lower layers of LLM Vampire discover services, interrogate their capabilities, maintain an inventory, route requests and expose a stable API.

This specification defines the higher-level intelligence layer built above that infrastructure.

The higher-level system shall allow clients to request an outcome without selecting a specific model, machine or provider. LLM Vampire shall select and combine appropriate services, manage context, divide complex work into tasks, verify results and present the operation as one coherent intelligence service.

The central product principle is:

> A client asks LLM Vampire for an outcome, not for a particular model.

LLM Vampire shall transform a collection of independent model servers into a coordinated local intelligence system.

---

# 2. Product Vision

A local network may contain several AI services with different characteristics:

* one fast small model;
* one large reasoning model;
* one coding model;
* one vision-capable model;
* several identical models on different machines;
* embedding and reranking services;
* speech, image or document-processing services;
* cloud services permitted by policy.

Without an orchestration layer, users must understand model names, endpoints, capabilities, context limits and current machine availability.

LLM Vampire shall hide this complexity.

Applications shall connect to one stable service and request capabilities such as:

```text
vampire:auto
vampire:fast
vampire:reason
vampire:code
vampire:vision
vampire:verified
vampire:council
```

LLM Vampire shall determine how each request should be completed.

---

# 3. Goals

LLM Vampire shall:

1. Select suitable models and services automatically.
2. Combine multiple models to improve answer quality.
3. Divide complex requests into independently executable tasks.
4. preserve context when requests move between models.
5. Verify outputs using critics, judges, tests and schemas.
6. Support persistent agents independent of individual models.
7. Expose higher-level functionality through stable APIs.
8. Remain compatible with ordinary OpenAI-compatible clients.
9. Operate locally and privately by default.
10. Learn which available services perform best for particular work.
11. Continue functioning when individual models or machines disappear.
12. Make orchestration visible, controllable and auditable.

---

# 4. Non-Goals

LLM Vampire shall not:

* implement its own inference engine;
* directly control GPUs unless a provider explicitly exposes that capability;
* require every provider to implement the same native API;
* assume that a particular model is always available;
* guarantee that generated information is true;
* grant tools or agents unrestricted operating-system access by default;
* send private information to external services without explicit policy permission;
* silently change a normal OpenAI-compatible request into an expensive multi-model operation;
* depend permanently on LM Studio, Ollama or any other single provider.

---

# 5. Terminology

## 5.1 Provider

A software platform exposing one or more AI services.

Examples include LM Studio, llmster, llama.cpp, Ollama, LocalAI and vLLM.

## 5.2 Node

A reachable provider instance on a particular machine and endpoint.

## 5.3 Service

A callable AI capability exposed by a node.

A service may be:

* text generation;
* embeddings;
* reranking;
* vision;
* speech recognition;
* speech generation;
* image generation;
* moderation;
* document parsing.

## 5.4 Model

A particular model available through a service.

## 5.5 Capability

A machine-readable property of a service or model, such as:

* text generation;
* reasoning;
* tool calling;
* structured output;
* vision input;
* embedding generation;
* maximum context length;
* supported languages.

## 5.6 Profile

A logical description of the capability required by a request.

Examples:

```text
vampire:fast
vampire:code
vampire:verified
```

A profile is not tied to a specific model.

## 5.7 Strategy

The method used to execute a request.

Examples include single-model execution, race, council and critic-refiner.

## 5.8 Task

A durable unit of work with inputs, state, outputs and execution history.

## 5.9 Workflow

A graph of dependent tasks.

## 5.10 Agent

A persistent identity containing instructions, memory, permissions, tools and a preferred execution profile.

## 5.11 Judge

A model or deterministic process that compares candidate outputs.

## 5.12 Critic

A model or deterministic process that identifies defects in an output.

---

# 6. Architectural Principles

## 6.1 Provider Neutrality

All higher-level functionality shall depend on normalized capabilities rather than provider names.

Provider-specific adapters shall translate native functionality into the LLM Vampire capability model.

## 6.2 Compatibility First

Ordinary OpenAI-compatible requests shall continue to function without Vampire-specific fields.

Advanced orchestration shall be opt-in through:

* virtual model names;
* Vampire request fields;
* Vampire headers;
* dedicated task and workflow APIs.

## 6.3 Graceful Degradation

When a preferred strategy cannot be completed, LLM Vampire shall either:

1. use an explicitly permitted fallback;
2. return a clear explanation that requirements could not be satisfied.

It shall not silently weaken security, privacy or verification requirements.

## 6.4 Local First

Local and trusted services shall be preferred unless policy permits external services.

## 6.5 Observable Orchestration

Users shall be able to determine:

* which strategy was used;
* which services participated;
* how long each stage took;
* whether fallbacks occurred;
* which checks were completed;
* how the final result was selected.

Private chain-of-thought content shall not be stored or exposed. Operational summaries and explicit critiques may be retained.

## 6.6 Least Privilege

Models, workflows and agents shall receive only the tools, data and permissions necessary for the current task.

## 6.7 Outcome-Oriented Requests

Clients should specify desired characteristics and constraints rather than infrastructure details.

---

# 7. Logical Architecture

```text
Applications, users and agents
              │
              ▼
┌──────────────────────────────────────────────┐
│              LLM Vampire Gateway             │
│ OpenAI compatibility │ Task API │ Agent API │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│          Intelligence Orchestration          │
│                                              │
│ Intent classification                        │
│ Profile resolution                           │
│ Task decomposition                           │
│ Strategy selection                           │
│ Execution graph                              │
│ Candidate generation                         │
│ Judging, criticism and verification           │
│ Result synthesis                             │
└──────────────────────┬───────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   Context service  Tool service  Policy engine
          │            │            │
          └────────────┼────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│         Capability Registry and Router       │
│ Inventory │ Health │ Performance │ Routing  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
 LM Studio │ llmster │ Ollama │ llama.cpp │ others
```

---

# 8. Capability Registry

## 8.1 Normalized Capability Record

Each discovered service shall be represented by a normalized record.

```json
{
  "service_id": "office-pc:1234/qwen3-14b",
  "node_id": "office-pc:1234",
  "provider": "lmstudio",
  "model": "qwen3-14b",
  "modalities": {
    "input": ["text"],
    "output": ["text"]
  },
  "capabilities": {
    "chat": true,
    "completion": true,
    "reasoning": true,
    "tool_calling": true,
    "structured_output": true,
    "vision": false,
    "embeddings": false
  },
  "limits": {
    "context_tokens": 32768,
    "maximum_output_tokens": 8192,
    "parallel_requests": 2
  },
  "operational": {
    "available": true,
    "loaded": true,
    "trusted": true,
    "local": true
  },
  "performance": {
    "median_ttft_ms": 740,
    "median_tokens_per_second": 31.4
  }
}
```

## 8.2 Capability Sources

Capabilities may be established through:

* provider metadata;
* administrator configuration;
* model metadata;
* active capability probes;
* historical execution results;
* benchmark suites.

## 8.3 Confidence

Inferred capabilities shall include a confidence value and source.

A model shall not be selected for a mandatory capability when support is uncertain unless the request permits experimental selection.

---

# 9. Virtual Models and Profiles

LLM Vampire shall expose logical model profiles.

## 9.1 Required Profiles

### `vampire:auto`

Select the best available execution plan using request content, capability requirements and policy.

### `vampire:fast`

Prefer low latency and minimal orchestration.

### `vampire:reason`

Prefer models with demonstrated reasoning performance.

### `vampire:code`

Prefer models with coding, tool-use and structured-output capability.

### `vampire:vision`

Require image-input capability.

### `vampire:private`

Use only nodes permitted for the request’s privacy classification.

### `vampire:verified`

Generate an answer and perform one or more independent verification steps.

### `vampire:council`

Obtain independent analyses from multiple models and synthesise them.

### `vampire:cheap`

Minimise estimated monetary, energy or compute cost.

### `vampire:large-context`

Prefer services capable of accepting the full context without compression.

## 9.2 Custom Profiles

Administrators shall be able to define custom profiles.

```yaml
profiles:
  legal-review:
    required:
      structured_output: true
      context_tokens: 64000
    strategy: critic_refine
    privacy:
      maximum_classification: confidential
      external_services: false
    verification:
      minimum_critics: 1
      citation_check: true
```

## 9.3 Profile Resolution

Profile resolution shall produce an explicit execution plan containing:

* required capabilities;
* preferred capabilities;
* eligible services;
* selected strategy;
* verification requirements;
* privacy constraints;
* resource limits;
* fallback rules.

---

# 10. Intent and Requirement Detection

For `vampire:auto`, LLM Vampire shall inspect the request and infer likely requirements.

It may classify requests as:

* conversation;
* summarisation;
* extraction;
* classification;
* coding;
* mathematical reasoning;
* document analysis;
* creative writing;
* translation;
* vision analysis;
* tool execution;
* planning;
* research;
* high-risk or sensitive work.

Intent detection shall be advisory.

Explicit client requirements shall override inferred preferences.

Inferred intent shall never override mandatory policy restrictions.

---

# 11. Execution Strategies

## 11.1 Single

Send the request to one selected service.

Use when:

* low latency is important;
* the task is simple;
* only one eligible service exists;
* additional model execution is not justified.

## 11.2 Fallback

Attempt services in ordered sequence until one succeeds.

Fallback triggers may include:

* node unavailable;
* model unloaded;
* timeout;
* context too large;
* malformed response;
* tool-call failure;
* policy rejection.

## 11.3 Race

Send the request to multiple services concurrently and return the first result satisfying acceptance conditions.

The remaining requests should be cancelled when possible.

## 11.4 Best-of-N

Generate multiple candidates and select the strongest candidate using a judge.

The judge shall receive the task, selection criteria and candidate outputs.

## 11.5 Council

Request independent analyses from several services.

A synthesiser shall:

1. identify common conclusions;
2. identify disagreements;
3. resolve or expose unresolved conflicts;
4. produce one coherent result.

## 11.6 Debate

One or more models propose an answer and other models challenge its assumptions or conclusions.

A resolver shall produce the final result.

Debate shall be bounded by:

* maximum rounds;
* maximum token budget;
* maximum execution time.

## 11.7 Critic-Refine

A producer generates a draft.

A critic identifies defects according to an explicit rubric.

A refiner produces a revised result.

The critic should not rewrite the entire result unless specifically requested.

## 11.8 Planner-Executor

A planner decomposes a complex objective into tasks.

Executors complete the tasks.

A controller tracks dependencies and integrates the results.

## 11.9 Map-Reduce

A large input is divided into sections.

Multiple workers process sections independently.

A reducer combines their outputs.

This strategy is intended for:

* large document collections;
* repository analysis;
* log analysis;
* batch classification;
* distributed summarisation.

## 11.10 Specialist Pipeline

Different profiles are assigned to sequential stages.

Example:

```text
Planner → Researcher → Implementer → Tester → Reviewer
```

Each stage shall receive only the context required for its function.

## 11.11 Deterministic Workflow

A predefined workflow executes without model-generated decomposition.

This shall be preferred where repeatability is more important than flexibility.

---

# 12. Orchestration Request Interface

Advanced orchestration shall be available through the OpenAI-compatible interface.

```json
{
  "model": "vampire:verified",
  "messages": [
    {
      "role": "user",
      "content": "Review this proposed database migration."
    }
  ],
  "vampire": {
    "strategy": "critic_refine",
    "requirements": {
      "minimum_context_tokens": 16000,
      "tool_calling": true
    },
    "privacy": {
      "classification": "confidential",
      "external_services": false
    },
    "verification": {
      "schema_validation": true,
      "minimum_critics": 1
    },
    "limits": {
      "maximum_models": 3,
      "maximum_duration_seconds": 180,
      "maximum_total_tokens": 50000
    },
    "fallback": {
      "allowed": true,
      "minimum_quality": "standard"
    }
  }
}
```

Unknown Vampire fields shall not be forwarded to providers.

---

# 13. Task API

Long-running and multi-stage work shall use a durable task API.

## 13.1 Create Task

```http
POST /vampire/v1/tasks
```

```json
{
  "objective": "Analyse this repository and propose a release plan.",
  "profile": "vampire:code",
  "strategy": "planner_executor",
  "inputs": [
    {
      "type": "repository",
      "reference": "local://repositories/example"
    }
  ],
  "limits": {
    "maximum_duration_seconds": 900,
    "maximum_parallel_tasks": 4
  }
}
```

## 13.2 Task States

A task shall have one of the following states:

```text
created
planning
queued
running
waiting
verifying
completed
partially_completed
failed
cancelled
```

## 13.3 Required Task Operations

```http
POST   /vampire/v1/tasks
GET    /vampire/v1/tasks/{task_id}
GET    /vampire/v1/tasks/{task_id}/events
GET    /vampire/v1/tasks/{task_id}/result
POST   /vampire/v1/tasks/{task_id}/cancel
POST   /vampire/v1/tasks/{task_id}/retry
```

## 13.4 Task Event Stream

Tasks shall expose a stream of operational events.

Events may include:

* plan created;
* subtask started;
* service selected;
* fallback activated;
* candidate produced;
* verification failed;
* refinement started;
* task completed.

Events shall not expose hidden reasoning traces.

---

# 14. Task Decomposition

## 14.1 Plan Representation

Plans shall be represented as directed acyclic graphs unless a bounded loop is explicitly permitted.

```json
{
  "tasks": [
    {
      "id": "inspect",
      "objective": "Inspect repository architecture",
      "profile": "vampire:code",
      "depends_on": []
    },
    {
      "id": "test",
      "objective": "Evaluate test coverage",
      "profile": "vampire:code",
      "depends_on": ["inspect"]
    },
    {
      "id": "release",
      "objective": "Produce release recommendation",
      "profile": "vampire:reason",
      "depends_on": ["inspect", "test"]
    }
  ]
}
```

## 14.2 Plan Validation

Before execution, LLM Vampire shall validate:

* dependency references;
* cycles;
* required capabilities;
* permissions;
* tool availability;
* privacy constraints;
* estimated resource usage;
* maximum task count.

## 14.3 Human Approval

Policies may require approval before:

* executing tools;
* contacting external services;
* modifying files;
* running shell commands;
* exceeding resource limits;
* processing highly sensitive data.

---

# 15. Context Service

## 15.1 Context Independence

Conversation and task context shall belong to LLM Vampire rather than to a particular model.

This shall allow the selected model to change without losing relevant state.

## 15.2 Context Types

The context service shall support:

* conversation history;
* task state;
* user-provided documents;
* retrieved knowledge;
* agent memory;
* tool results;
* summaries;
* structured facts;
* temporary working data.

## 15.3 Context Assembly

Before each model call, LLM Vampire shall construct a context package according to:

* model context limit;
* task requirements;
* privacy policy;
* relevance;
* recency;
* token budget;
* stage role.

## 15.4 Context Compression

When full context cannot fit, LLM Vampire may:

1. remove irrelevant material;
2. substitute existing summaries;
3. generate new summaries;
4. divide work across tasks;
5. select a larger-context model;
6. return an explicit context-limit error.

Lossy compression shall be recorded in execution metadata.

## 15.5 Context Isolation

Context belonging to one user, agent, realm or organisation shall not be accessible to another unless explicitly shared.

---

# 16. Memory

## 16.1 Memory Categories

LLM Vampire shall distinguish:

* session memory;
* conversation memory;
* agent memory;
* user memory;
* organisational memory;
* task memory;
* retrieved knowledge.

## 16.2 Memory Entries

A memory entry should contain:

```json
{
  "memory_id": "mem_123",
  "scope": "agent",
  "owner": "agent_sysadmin",
  "content": "Production changes require explicit approval.",
  "source": "user_instruction",
  "created_at": "2026-07-31T04:00:00Z",
  "expires_at": null,
  "sensitivity": "confidential",
  "confidence": 1.0
}
```

## 16.3 Memory Controls

Users shall be able to:

* inspect retained memories;
* correct memories;
* delete memories;
* disable memory;
* set expiration;
* restrict memory scope;
* prevent selected content from being retained.

Models shall not be allowed to declare arbitrary generated assumptions as confirmed user facts.

---

# 17. Retrieval and Knowledge Services

LLM Vampire may integrate document and vector-search services.

The retrieval pipeline may contain:

```text
Query analysis
→ Query rewriting
→ Embedding
→ Candidate retrieval
→ Reranking
→ Context assembly
→ Generation
→ Citation verification
```

The system shall preserve source identity and location so outputs can cite supporting material.

Retrieval results shall be treated as untrusted input and shall not automatically receive tool authority.

---

# 18. Verification Framework

## 18.1 Verification Methods

LLM Vampire shall support:

* independent model review;
* multi-model agreement;
* schema validation;
* deterministic rule checks;
* code execution;
* unit and integration tests;
* citation checking;
* source-grounding checks;
* mathematical evaluation;
* tool-result confirmation;
* policy validation.

## 18.2 Verification Levels

### None

No additional verification.

### Basic

Validate response shape and obvious execution errors.

### Reviewed

Use one independent critic or deterministic test.

### Verified

Use multiple checks appropriate to the task.

### High Assurance

Require predefined checks, agreement thresholds and human approval where configured.

## 18.3 Confidence Reporting

Confidence shall not be represented as an unsupported percentage generated by a model.

It should be derived from observable evidence such as:

* number of completed checks;
* candidate agreement;
* test results;
* source support;
* unresolved disagreements;
* capability confidence.

Example:

```json
{
  "verification": {
    "level": "verified",
    "checks_completed": 4,
    "checks_failed": 0,
    "candidate_agreement": "high",
    "unresolved_disagreements": [],
    "confidence_basis": [
      "two independent candidates agreed",
      "schema validation passed",
      "referenced tests passed"
    ]
  }
}
```

## 18.4 Verification Failure

When verification fails, the system may:

1. refine the result;
2. try another model;
3. request additional information;
4. return candidates with disagreements identified;
5. fail the task.

It shall not label an unverified result as verified.

---

# 19. Structured Output

LLM Vampire shall support output schemas independent of provider implementation.

When a provider lacks native schema support, LLM Vampire may use:

* constrained prompting;
* parser repair;
* retry with validation feedback;
* another capable model.

Schema validation results shall be included in execution metadata.

The original invalid output may be retained for diagnostics according to logging policy.

---

# 20. Tools

## 20.1 Tool Registry

Tools shall be represented using normalized metadata:

```json
{
  "tool_id": "filesystem.read",
  "description": "Read an authorised file",
  "input_schema": {},
  "permissions": ["filesystem:read"],
  "risk": "low",
  "execution_location": "vampire-host"
}
```

## 20.2 Tool Execution

Models shall request tool calls.

LLM Vampire, not the model provider, shall decide whether a tool call is permitted.

## 20.3 Approval Modes

Tools shall support:

* automatically approved;
* approved within defined boundaries;
* approval required;
* prohibited.

## 20.4 Tool Results

Tool results shall be:

* associated with the requesting task;
* size limited;
* sanitised where appropriate;
* treated as untrusted data;
* recorded in the audit trail.

---

# 21. Persistent Agents

## 21.1 Agent Definition

An agent shall be independent of any particular model.

```json
{
  "agent_id": "ubuntu-sysadmin",
  "name": "Ubuntu Systems Administrator",
  "instructions": "Maintain authorised Ubuntu systems safely.",
  "profile": "vampire:reason",
  "fallback_profile": "vampire:fast",
  "memory_scope": "agent",
  "tools": [
    "filesystem.read",
    "package.inspect",
    "shell.propose"
  ],
  "approval_policy": "confirm_mutations",
  "privacy_policy": "local_only"
}
```

## 21.2 Agent Responsibilities

The agent runtime shall manage:

* identity;
* instructions;
* conversation state;
* memory;
* tools;
* permissions;
* active tasks;
* preferred profiles;
* model transitions;
* failure recovery.

## 21.3 Model Independence

An agent may use different models for different stages without changing its external identity.

Example:

```text
Small model: classify request
Reasoning model: create plan
Coding model: produce commands
Critic model: inspect plan
Small model: explain result
```

## 21.4 Agent API

```http
POST /vampire/v1/agents
GET  /vampire/v1/agents
GET  /vampire/v1/agents/{agent_id}
POST /vampire/v1/agents/{agent_id}/messages
GET  /vampire/v1/agents/{agent_id}/tasks
```

---

# 22. Learning Router

## 22.1 Purpose

The router shall gradually learn which services perform best for particular tasks on the current network.

## 22.2 Metrics

The system may record:

* task category;
* successful completion;
* latency;
* time to first token;
* output rate;
* structured-output success;
* tool-call success;
* test pass rate;
* critic result;
* judge ranking;
* user retry;
* user acceptance;
* resource consumption;
* provider failure rate.

## 22.3 Selection Scores

Service ranking may combine:

```text
Capability match
× Quality history
× Availability
× Trust
× Latency preference
× Cost preference
× Privacy eligibility
```

Mandatory requirements shall be applied before ranking.

## 22.4 Feedback Safety

A model shall not become highly ranked solely because another instance of the same model judges it favourably.

Evaluation should use diverse evidence where practical.

## 22.5 Administrator Control

Administrators shall be able to:

* inspect rankings;
* reset learned data;
* disable adaptive routing;
* pin services;
* exclude services;
* define minimum sample sizes;
* use static routing only.

---

# 23. Policy and Privacy

## 23.1 Data Classifications

The initial system should support:

```text
public
internal
confidential
restricted
```

## 23.2 Node Trust Levels

Nodes should support:

```text
untrusted
discovered
approved
trusted
privileged
```

## 23.3 Routing Rule

A request may be routed only to nodes whose trust and location satisfy its data classification.

## 23.4 External Providers

External services shall be disabled by default.

When enabled, policy shall specify:

* permitted providers;
* permitted data classifications;
* permitted users or agents;
* cost limits;
* logging requirements.

## 23.5 Secrets

Secrets shall not be inserted into model context unless required and explicitly permitted.

Tool credentials shall remain inside the tool-execution boundary wherever possible.

## 23.6 Logs

Logging shall be configurable separately for:

* request metadata;
* prompts;
* responses;
* tool calls;
* memory operations;
* orchestration events.

Prompt and response logging should be disabled by default for confidential and restricted requests.

---

# 24. Resource Governance

Each request, task or agent shall be subject to configurable limits:

* maximum participating models;
* maximum subtasks;
* maximum parallel calls;
* maximum total tokens;
* maximum execution duration;
* maximum retries;
* maximum debate rounds;
* maximum monetary cost;
* maximum energy or compute score;
* maximum retained context;
* maximum tool calls.

The orchestrator shall stop execution when a hard limit is reached.

Partial results may be returned when policy permits.

---

# 25. Failure Handling

LLM Vampire shall distinguish:

* provider unavailable;
* model unavailable;
* capability mismatch;
* context overflow;
* timeout;
* malformed output;
* failed verification;
* policy rejection;
* tool failure;
* exhausted resource limit;
* cancelled task;
* orchestration failure.

Errors returned through OpenAI-compatible endpoints shall use compatible error envelopes.

Vampire-specific metadata may provide additional details.

Example:

```json
{
  "error": {
    "message": "No eligible local vision service is currently available.",
    "type": "vampire_capability_unavailable",
    "code": "vision_service_unavailable"
  },
  "vampire": {
    "required_capability": "vision",
    "eligible_nodes": 0,
    "external_fallback_permitted": false
  }
}
```

---

# 26. Result Metadata

Responses produced through orchestration should include optional metadata.

```json
{
  "vampire": {
    "request_id": "req_123",
    "profile": "vampire:verified",
    "strategy": "critic_refine",
    "participating_services": 2,
    "fallbacks": 0,
    "duration_ms": 18450,
    "verification": {
      "level": "reviewed",
      "passed": true
    }
  }
}
```

OpenAI-compatible clients that ignore this field shall continue to function.

Equivalent summary headers may include:

```text
X-Vampire-Request-ID
X-Vampire-Profile
X-Vampire-Strategy
X-Vampire-Service-Count
X-Vampire-Fallback
X-Vampire-Verification
```

Sensitive infrastructure details shall be omitted unless the caller is authorised.

---

# 27. Dashboard Requirements

The dashboard shall provide views for:

## 27.1 Services

* nodes;
* providers;
* models;
* capabilities;
* availability;
* health;
* current load.

## 27.2 Profiles

* built-in profiles;
* custom profiles;
* capability requirements;
* strategies;
* fallback rules.

## 27.3 Tasks

* active tasks;
* execution graphs;
* current stage;
* participating services;
* verification state;
* task history.

## 27.4 Agents

* configured agents;
* permissions;
* tools;
* active tasks;
* memory usage;
* selected profiles.

## 27.5 Performance

* latency;
* throughput;
* failures;
* model rankings;
* task success;
* verification outcomes.

## 27.6 Governance

* node trust;
* privacy classifications;
* external-provider policy;
* tool approvals;
* resource limits;
* audit events.

---

# 28. Observability

LLM Vampire shall expose structured metrics for:

* requests by profile;
* requests by strategy;
* service selection;
* service latency;
* provider errors;
* fallback frequency;
* token usage;
* task duration;
* verification failures;
* tool calls;
* queue depth;
* cache effectiveness;
* coalesced requests.

Distributed task operations shall use a common request and task identifier.

Tracing shall show orchestration stages without recording hidden model reasoning.

---

# 29. Functional Requirements

## FR-001 Provider Independence

Higher-level services shall operate against normalized capability records rather than hard-coded provider names.

## FR-002 Profile Resolution

The system shall resolve each virtual profile into an executable plan.

## FR-003 Automatic Selection

The system shall select an eligible service without requiring the client to provide a physical model name.

## FR-004 Multi-Model Strategies

The system shall support single, fallback, race, best-of-N, council and critic-refine strategies.

## FR-005 Durable Tasks

The system shall support durable, inspectable and cancellable tasks.

## FR-006 Task Graphs

The system shall support dependency-based task execution.

## FR-007 Context Portability

Context shall remain available when execution moves between models.

## FR-008 Verification

The system shall support model-based and deterministic verification.

## FR-009 Persistent Agents

Agents shall retain identity and state independently of the model serving each request.

## FR-010 Tool Governance

All tool execution shall pass through policy enforcement.

## FR-011 Privacy Routing

Requests shall be routed only to services permitted for their data classification.

## FR-012 Resource Limits

Every orchestration operation shall enforce configured resource limits.

## FR-013 Graceful Degradation

The system shall use declared fallback rules when preferred services are unavailable.

## FR-014 Auditability

The system shall retain operational records explaining how a result was produced.

## FR-015 Adaptive Routing

The system may use historical performance to improve future service selection.

## FR-016 User Control

Users and administrators shall be able to disable orchestration and select a specific service.

## FR-017 Streaming

Strategies capable of producing a single continuous answer should support streaming.

For multi-candidate strategies, the system may delay final output until selection or synthesis is complete.

## FR-018 Cancellation

Cancellation shall propagate to active provider requests and tools where supported.

---

# 30. Non-Functional Requirements

## NFR-001 Availability

Failure of one provider shall not terminate the gateway when other eligible providers remain.

## NFR-002 Extensibility

New providers and strategies shall be installable without modifying the orchestration core.

## NFR-003 Performance

Single-model proxy overhead should remain small relative to model inference latency.

## NFR-004 Security

All control, task, agent and memory APIs shall require authentication when exposed beyond localhost.

## NFR-005 Privacy

No request content shall leave its permitted trust boundary.

## NFR-006 Determinism

Where deterministic workflows are selected, identical inputs and configuration should produce equivalent execution plans.

## NFR-007 Explainability

The system shall explain operational decisions without exposing private reasoning traces.

## NFR-008 Portability

The core system should run on Windows, macOS and Linux.

## NFR-009 Recoverability

Durable tasks shall recover or enter a clearly failed state after process restart.

## NFR-010 Backward Compatibility

Existing OpenAI-compatible clients shall not require Vampire-specific support.

---

# 31. Plugin Interfaces

The following components should use explicit plugin interfaces:

```text
ProviderAdapter
CapabilityProbe
RoutingStrategy
OrchestrationStrategy
IntentClassifier
ContextProvider
MemoryStore
Retriever
Reranker
ToolProvider
Verifier
Judge
PolicyProvider
MetricsStore
TaskStore
```

Each interface shall have a versioned contract.

A plugin failure shall be isolated from the main gateway where practical.

---

# 32. Suggested Internal Components

```text
vampire/
├── providers/
│   ├── base.py
│   ├── lmstudio.py
│   ├── openai_compatible.py
│   ├── ollama.py
│   └── llamacpp.py
├── capabilities/
│   ├── registry.py
│   ├── probes.py
│   └── profiles.py
├── orchestration/
│   ├── planner.py
│   ├── executor.py
│   ├── strategies/
│   ├── judge.py
│   └── synthesiser.py
├── tasks/
│   ├── models.py
│   ├── graph.py
│   ├── scheduler.py
│   └── store.py
├── context/
│   ├── assembler.py
│   ├── compression.py
│   └── retrieval.py
├── memory/
│   ├── service.py
│   └── stores/
├── agents/
│   ├── models.py
│   ├── runtime.py
│   └── service.py
├── tools/
│   ├── registry.py
│   ├── executor.py
│   └── approvals.py
├── verification/
│   ├── schemas.py
│   ├── critics.py
│   ├── consensus.py
│   └── tests.py
└── policy/
    ├── engine.py
    ├── privacy.py
    └── resources.py
```

---

# 33. Delivery Roadmap

## Phase 1 — Provider-Neutral Foundation

* rename product concepts from LM Studio-specific to LLM-service terminology;
* implement normalized service and capability records;
* preserve the LM Studio implementation as a provider adapter;
* support manually registered OpenAI-compatible endpoints;
* expose normalized model inventory.

## Phase 2 — Profiles and Intelligent Routing

* implement built-in virtual profiles;
* profile resolution;
* task-intent classification;
* capability-aware selection;
* policy-aware fallback;
* routing explanation metadata.

## Phase 3 — Multi-Model Orchestration

* race;
* best-of-N;
* council;
* critic-refine;
* configurable judges;
* resource budgets;
* orchestration dashboard.

## Phase 4 — Durable Tasks and Workflows

* task API;
* persistent task store;
* execution graphs;
* planner-executor strategy;
* map-reduce;
* cancellation and recovery;
* task event streaming.

## Phase 5 — Verification

* schema validation;
* deterministic validators;
* critic framework;
* consensus reporting;
* citation checking;
* code and test verification adapters.

## Phase 6 — Context and Memory

* model-independent conversations;
* context assembly;
* context compression;
* scoped memory;
* memory inspection and deletion;
* document retrieval.

## Phase 7 — Tool Runtime

* tool registry;
* permission model;
* approval workflows;
* sandboxed execution;
* tool audit trail.

## Phase 8 — Persistent Agents

* agent definitions;
* agent conversations;
* agent memory;
* agent task management;
* model-independent agent execution.

## Phase 9 — Adaptive Intelligence

* historical quality metrics;
* learned service rankings;
* task-specific performance profiles;
* automatic strategy recommendation;
* administrator-controlled learning.

---

# 34. Minimum Viable Higher-Level Product

The first useful higher-level release shall include:

1. provider-neutral capability records;
2. `vampire:auto`;
3. `vampire:fast`;
4. `vampire:code`;
5. `vampire:verified`;
6. single, fallback and critic-refine strategies;
7. one independent judge interface;
8. JSON Schema validation;
9. orchestration metadata;
10. strict privacy routing;
11. token and duration budgets;
12. dashboard visibility.

This release does not require autonomous agents, persistent memory or arbitrary workflow generation.

---

# 35. MVP Acceptance Criteria

The MVP shall be accepted when all the following are demonstrated:

1. Two different compatible providers can be registered.
2. Their capabilities are represented through the same normalized schema.
3. A client can request `vampire:auto` without naming a physical model.
4. The router selects an eligible model based on capabilities.
5. A failed provider request falls back to another eligible provider.
6. `vampire:verified` produces a draft, obtains an independent critique and produces a refined answer.
7. A structured-output request is validated against a JSON Schema.
8. A confidential request is never sent to a node that policy marks as ineligible.
9. A hard token or duration limit stops additional orchestration.
10. The response identifies the profile, strategy, verification state and number of participating services.
11. An ordinary OpenAI-compatible request still works without Vampire-specific fields.
12. The dashboard shows the execution path without exposing hidden reasoning.

---

# 36. Future Possibilities

The architecture should leave room for:

* federated Vampire installations;
* trusted household or organisational compute pools;
* distributed task queues;
* energy-aware routing;
* scheduled agents;
* voice interaction;
* multimodal workflows;
* collaborative human approval;
* encrypted shared memory;
* benchmark exchange between Vampire nodes;
* private marketplace-style service sharing;
* local and cloud hybrid execution;
* execution across disconnected or intermittently available machines.

These features are outside the initial implementation scope but shall not be prevented by early architectural decisions.

---

# 37. Final Product Definition

LLM Vampire is not merely a reverse proxy or model load balancer.

It is:

> A provider-neutral intelligence orchestration system that discovers available AI services, understands their capabilities, selects and combines them, preserves context, verifies results and exposes the collection as one coherent local intelligence.

The underlying models may appear, disappear or change.

The intelligence service presented to the user remains stable.
