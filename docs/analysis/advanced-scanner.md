# Advanced LM Studio Resource Scanner — Agent Implementation Summary

## Objective

Implement a black-box systems scanner that determines the number of independently usable GPU-backed inference resources across multiple LM Studio nodes.

The scanner must not depend on GPU UUIDs, OS-level GPU APIs, `nvidia-smi`, ROCm, hostnames, MAC addresses, or IP addresses as primary identity signals. Instead, it must interrogate each LM Studio node through its API, load calibration models, run controlled inference workloads, compare performance under solo and concurrent load, and infer which nodes share the same underlying compute resource.

The final output should be a set of inferred GPU groups, not a list of nodes.

Example result:

```json
{
  "estimated_unique_gpu_groups": 3,
  "groups": [
    {
      "gpu_group_id": "gpu-group-1",
      "nodes": ["node-a", "node-b"],
      "confidence": "high",
      "classification": "shared_compute"
    },
    {
      "gpu_group_id": "gpu-group-2",
      "nodes": ["node-c"],
      "confidence": "medium",
      "classification": "independent_compute"
    },
    {
      "gpu_group_id": "gpu-group-3",
      "nodes": ["node-d", "node-e"],
      "confidence": "high",
      "classification": "shared_compute"
    }
  ]
}
```

## Core Principle

LM Studio can identify loaded model instances and report inference/load performance, but it does not expose a physical GPU identity through the public REST API.

Therefore:

```text
Do not ask: "What GPU UUID does this node use?"

Ask instead: "Does this node behave as if it shares the same constrained compute resource as another node?"
```

The scanner must treat GPU identity as an inferred resource grouping problem.

## Inputs

The scanner receives a list of LM Studio node endpoints:

```json
{
  "nodes": [
    {
      "node_id": "node-a",
      "base_url": "http://10.0.0.11:1234"
    },
    {
      "node_id": "node-b",
      "base_url": "http://10.0.0.12:1234"
    }
  ],
  "calibration_model": "qwen/qwen3-4b",
  "test_context_length": 32768,
  "max_tokens": 512,
  "repetitions": 5
}
```

`node_id` is a scanner-local identifier only. It is not proof of physical resource uniqueness.

## LM Studio API Operations

For each node, the scanner should use:

```http
GET /api/v1/models
```

Purpose:

```text
Discover available models.
Determine whether the calibration model exists.
Determine whether the model is already loaded.
Capture model metadata where available.
```

Then:

```http
POST /api/v1/models/load
```

Purpose:

```text
Load the calibration model with controlled settings.
Capture load status, instance_id, load_time_seconds, and applied load_config.
```

Then:

```http
POST /api/v1/chat
```

Purpose:

```text
Run controlled benchmark prompts.
Capture output token count, tokens_per_second, time_to_first_token_seconds, generation duration, and model load timing if present.
```

Optionally:

```http
POST /api/v1/models/unload
```

Purpose:

```text
Reset test state after probing.
Avoid leaving calibration models resident if the scanner is running in discovery mode.
```

## Calibration Model Selection

The calibration model must be large enough to create measurable contention.

Bad calibration model:

```text
A tiny model that fits trivially everywhere and produces no meaningful contention.
```

Good calibration model:

```text
A model/context configuration that meaningfully uses GPU memory and generation compute but is still expected to load on healthy nodes.
```

Recommended properties:

```text
Same model on all nodes
Same quantization where possible
Same context length
Same load parameters
Same prompt
Same decoding parameters
Same max token count
Temperature set to 0
Streaming disabled unless precise streaming telemetry is required
```

## Load Configuration

Use a consistent load request.

Example:

```json
{
  "model": "qwen/qwen3-4b",
  "context_length": 32768,
  "flash_attention": true,
  "offload_kv_cache_to_gpu": true,
  "echo_load_config": true
}
```

Record the actual returned `load_config`. Do not assume the requested configuration was applied exactly.

The scanner must store both:

```text
requested_load_config
actual_load_config
```

If two nodes apply materially different load configurations, reduce confidence in direct performance comparisons.

## Benchmark Prompt

Use a deterministic prompt with enough output to measure stable throughput.

Example:

```json
{
  "model": "qwen/qwen3-4b",
  "messages": [
    {
      "role": "user",
      "content": "Write exactly 300 words about checksum validation in distributed systems."
    }
  ],
  "temperature": 0,
  "max_tokens": 512,
  "stream": false
}
```

The exact semantic content does not matter. The prompt must be:

```text
Fixed
Repeatable
Long enough to produce measurable generation
Not dependent on external tools
Not dependent on real-time knowledge
Not safety-sensitive
```

## Phase 1 — Node Discovery

For each node:

1. Call `GET /api/v1/models`.
2. Confirm the calibration model exists or can be loaded.
3. Capture available model metadata.
4. Mark node as unavailable if API is unreachable.
5. Mark node as unsuitable if calibration model cannot be found or loaded.

Output:

```json
{
  "node_id": "node-a",
  "reachable": true,
  "calibration_model_available": true,
  "models": [
    {
      "id": "qwen/qwen3-4b",
      "state": "loaded"
    }
  ]
}
```

## Phase 2 — Controlled Load Probe

For each suitable node:

1. Load the calibration model.
2. Capture response fields.
3. Verify load status is successful.
4. Store `instance_id`.
5. Store `load_time_seconds`.
6. Store `actual_load_config`.

Example:

```json
{
  "node_id": "node-a",
  "model_id": "qwen/qwen3-4b",
  "instance_id": "qwen/qwen3-4b",
  "load_status": "loaded",
  "load_time_seconds": 8.91,
  "actual_load_config": {
    "context_length": 32768,
    "flash_attention": true,
    "offload_kv_cache_to_gpu": true
  }
}
```

Important:

```text
instance_id identifies the LM Studio loaded model instance.
instance_id does not identify the physical GPU.
Do not deduplicate physical resources using instance_id.
```

## Phase 3 — Solo Baseline Probe

For each node:

1. Ensure the calibration model is loaded.
2. Run the benchmark prompt N times.
3. Capture runtime metrics for each run.
4. Compute median values.
5. Store median tokens/sec, TTFT, generation time, and token counts.

Example solo result:

```json
{
  "node_id": "node-a",
  "solo_baseline": {
    "runs": 5,
    "median_tokens_per_second": 54.2,
    "median_time_to_first_token_seconds": 0.22,
    "median_generation_time_seconds": 7.8,
    "median_output_tokens": 421
  }
}
```

Use medians, not means, because occasional load spikes or background tasks can distort averages.

## Phase 4 — Pairwise Concurrent Interference Probe

For every pair of suitable nodes `(A, B)`:

1. Ensure the calibration model is loaded on both nodes.
2. Start the benchmark request on both nodes at the same time.
3. Repeat N times.
4. Capture runtime metrics for both nodes.
5. Compare concurrent performance against solo baseline.

Example:

```json
{
  "pair": ["node-a", "node-b"],
  "solo": {
    "node-a": {
      "tokens_per_second": 54.2,
      "ttft_seconds": 0.22
    },
    "node-b": {
      "tokens_per_second": 55.1,
      "ttft_seconds": 0.21
    }
  },
  "concurrent": {
    "node-a": {
      "tokens_per_second": 27.4,
      "ttft_seconds": 0.71
    },
    "node-b": {
      "tokens_per_second": 28.0,
      "ttft_seconds": 0.69
    }
  }
}
```

Compute:

```text
tps_drop_a = 1 - concurrent_tps_a / solo_tps_a
tps_drop_b = 1 - concurrent_tps_b / solo_tps_b

ttft_multiplier_a = concurrent_ttft_a / solo_ttft_a
ttft_multiplier_b = concurrent_ttft_b / solo_ttft_b
```

Strong shared-resource signal:

```text
Both nodes suffer large throughput drops at the same time.
Both nodes show increased TTFT at the same time.
Both nodes show longer generation time at the same time.
```

Weak or no shared-resource signal:

```text
Both nodes maintain near-solo throughput during concurrent execution.
TTFT remains stable.
Generation duration remains stable.
```

## Phase 5 — Load Pressure Probe

The pairwise inference test detects compute contention. The load pressure test detects memory contention.

For every pair `(A, B)`:

1. Unload calibration model from both nodes if safe.
2. Load calibration model on A with a high-context or high-memory configuration.
3. While A holds the model loaded, attempt to load the same model/configuration on B.
4. Compare B’s load result against B’s solo load baseline.

Record:

```text
B loads successfully
B load fails
B load time increases materially
B load_config is reduced or altered
B succeeds only at lower context length
```

Interpretation:

```text
B loads alone but fails while A is loaded = strong shared-memory signal.
B loads with degraded config while A is loaded = probable shared-memory signal.
Both load normally with no timing/config impact = probable independent resources or insufficient test pressure.
```

## Phase 6 — Scoring

For each pair `(A, B)`, compute a shared-resource score.

Suggested scoring:

```text
+5 if B fails to load only while A is loaded
+4 if both nodes suffer >40% tokens/sec drop during concurrent benchmark
+3 if both nodes suffer >25% tokens/sec drop during concurrent benchmark
+3 if TTFT increases >3x on both nodes
+2 if generation time increases >2x on both nodes
+2 if load_time_seconds increases >2x under pair pressure
+2 if applied load_config is reduced only when the other node is loaded
+1 if intermittent failures occur only during pair testing

-3 if both nodes maintain >85% of solo throughput concurrently
-4 if both nodes load high-pressure configuration simultaneously without degradation
-5 if repeated pair tests show no correlated degradation
```

Suggested classification:

```text
score >= 7     => shared_compute_high_confidence
score 4 to 6   => shared_compute_medium_confidence
score 1 to 3   => inconclusive_possible_shared_compute
score -2 to 0  => inconclusive
score <= -3    => independent_compute_likely
score <= -6    => independent_compute_high_confidence
```

## Phase 7 — Clustering

Build an undirected graph:

```text
Node = LM Studio node
Edge = pair classified as shared_compute_medium_confidence or shared_compute_high_confidence
```

Then compute connected components.

Each connected component represents one inferred GPU-backed resource group.

Example pair classifications:

```text
A-B = shared
B-C = independent
C-D = shared
E = no shared edges
```

Groups:

```text
[A, B]
[C, D]
[E]
```

Estimated unique GPU groups:

```text
3
```

## Phase 8 — Resource Identity Generation

Create stable scanner-level resource IDs from inferred groups.

Example:

```text
gpu_group_id = "gpu-group-" + sha256(sorted(node_ids).join("|")).substring(0, 12)
```

For model resources:

```text
model_resource_id = gpu_group_id + ":" + model_id
```

Example:

```json
{
  "gpu_group_id": "gpu-group-a81ff92c120a",
  "model_resource_id": "gpu-group-a81ff92c120a:qwen/qwen3-4b",
  "nodes": ["node-a", "node-b"],
  "model_id": "qwen/qwen3-4b"
}
```

This is the resource key the scheduler should use for concurrency accounting.

## Output Schema

The scanner should output both a machine-readable summary and detailed evidence.

Example:

```json
{
  "scan_id": "scan-2026-06-14T10:30:00Z",
  "calibration_model": "qwen/qwen3-4b",
  "estimated_unique_gpu_groups": 2,
  "groups": [
    {
      "gpu_group_id": "gpu-group-a81ff92c120a",
      "nodes": ["node-a", "node-b"],
      "confidence": "high",
      "classification": "shared_compute",
      "model_resources": [
        {
          "model_id": "qwen/qwen3-4b",
          "model_resource_id": "gpu-group-a81ff92c120a:qwen/qwen3-4b"
        }
      ],
      "evidence": {
        "pairwise_tests": [
          {
            "pair": ["node-a", "node-b"],
            "score": 9,
            "median_tps_drop_node_a": 0.49,
            "median_tps_drop_node_b": 0.48,
            "ttft_multiplier_node_a": 3.2,
            "ttft_multiplier_node_b": 3.1,
            "load_pressure_result": "node_b_failed_while_node_a_loaded"
          }
        ]
      }
    },
    {
      "gpu_group_id": "gpu-group-d0d8e98f33b2",
      "nodes": ["node-c"],
      "confidence": "medium",
      "classification": "independent_compute",
      "model_resources": [
        {
          "model_id": "qwen/qwen3-4b",
          "model_resource_id": "gpu-group-d0d8e98f33b2:qwen/qwen3-4b"
        }
      ]
    }
  ],
  "warnings": [
    "This scan infers shared compute resources from observed contention. It does not prove physical GPU identity."
  ]
}
```

## Scheduler Integration

The scheduler should not count each LM Studio node as one independent resource.

Incorrect:

```text
resource = node_id + ":" + model_id
```

Correct:

```text
resource = gpu_group_id + ":" + model_id
```

Concurrency limits should attach to `model_resource_id`.

Example:

```json
{
  "model_resource_id": "gpu-group-a81ff92c120a:qwen/qwen3-4b",
  "max_concurrent_requests": 1,
  "backing_nodes": ["node-a", "node-b"]
}
```

If multiple nodes are in the same inferred group, they should be treated as alternate front doors to the same constrained resource, not independent capacity.

## Confidence Rules

The scanner must report confidence explicitly.

High confidence shared:

```text
Large correlated throughput degradation
AND/OR load failure under pair pressure
AND repeated across multiple runs
```

Medium confidence shared:

```text
Moderate correlated degradation
OR load timing/config degradation
BUT no hard failure
```

Inconclusive:

```text
Small differences
High variance
Different load configs
Unstable node performance
Calibration model too small
```

High confidence independent:

```text
Both nodes maintain near-solo throughput under concurrent benchmark
AND both can load high-pressure configurations simultaneously
AND repeated tests are stable
```

## Important Failure Modes

False positive risks:

```text
Shared CPU bottleneck
Shared RAM pressure
Shared disk loading bottleneck
Shared network bottleneck
Thermal throttling
Power limiting
Background workloads
Different model quantizations
Different LM Studio load configs
```

False negative risks:

```text
Calibration model too small
Context length too low
Benchmark too short
Insufficient concurrent pressure
GPU has enough spare capacity to hide contention
Caching effects
Only one node actually uses GPU while another falls back to CPU
```

Mitigations:

```text
Use a sufficiently large calibration model.
Use long enough generations to stabilise tokens/sec.
Repeat each test multiple times.
Use medians.
Capture actual load_config.
Run load pressure tests as well as inference tests.
Flag high variance as inconclusive.
```

## Privacy and Security Constraints

The scanner should not log prompt or response text unless explicitly enabled for debugging.

Store:

```text
node_id
model_id
load status
load timing
tokens/sec
TTFT
generation duration
token counts
error classes
classification results
```

Avoid storing:

```text
full prompt text
model response text
user data
secrets
API tokens
raw headers
```

Benchmark prompts should be synthetic and non-sensitive.

## Minimal Agent Task List

Implement the scanner in these modules:

```text
1. NodeClient
   - GET /api/v1/models
   - POST /api/v1/models/load
   - POST /api/v1/chat
   - POST /api/v1/models/unload

2. BenchmarkRunner
   - solo benchmark
   - concurrent pair benchmark
   - load pressure benchmark

3. MetricsReducer
   - median tokens/sec
   - median TTFT
   - median generation time
   - variance
   - degradation ratios

4. PairClassifier
   - score pairwise contention
   - classify shared, independent, or inconclusive

5. ResourceClusterer
   - build graph from shared pair edges
   - compute connected components
   - assign gpu_group_id

6. RegistryExporter
   - emit final JSON
   - expose model_resource_id for scheduler use
```

## Acceptance Criteria

The implementation is acceptable when it can:

```text
Discover all reachable LM Studio nodes.
Load the same calibration model across nodes.
Run repeatable solo benchmarks.
Run synchronized pairwise concurrent benchmarks.
Detect correlated performance degradation.
Detect load pressure failures or load_config degradation.
Cluster nodes into inferred compute groups.
Return estimated unique GPU-backed resource count.
Attach confidence and evidence to every grouping decision.
Avoid treating IP address, node ID, hostname, model ID, or LM Studio instance ID as proof of physical uniqueness.
```

## Core Rule for the Agent

The scanner does not identify GPUs directly.

It infers independently usable GPU-backed resources by observing whether LM Studio nodes contend with each other under controlled load.

The final answer is not:

```text
"These are the GPU UUIDs."
```

The final answer is:

```text
"These nodes appear to share or not share the same constrained inference resource, with this confidence and this evidence."
```
