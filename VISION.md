# Vision

`lmstudio-vampire` turns idle, LM Studio-compatible GPUs on a local network
into one governed, private AI service. It wakes on the LAN, discovers approved
inference endpoints, verifies their models and capabilities, and respects owner
tokens and policy before routing a single request. Behind a stable
OpenAI-compatible endpoint it load-balances, fails over, coalesces identical
prompts, and fuses answers across machines — optimizing for latency, privacy,
cost, and quality. Families share one GPU; businesses reuse workstation
capacity; classrooms and events become AI-capable with one strong host. The
owner decides when to contribute; users simply see working, local-first AI.
