"""lmstudio-vampire: private, owner-governed AI compute through LM Studio.

Vampire sits in front of one or more owner-approved LM Studio nodes as a
transparent OpenAI-compatible proxy and adds opt-in orchestration (discovery,
routing, fusion, policy). See IMPLEMENTATION-PLAN.md for the build roadmap.

Phase 0 provides the installable package, settings, CLI entry point, app factory,
core models, testing, linting, type checking, and CI scaffolding. Phase 1
provides the transparent ``/v1/*`` passthrough to a single configured LM Studio
node; multi-node routing and policy remain deliberately deferred to later
phases.
"""

__version__ = "0.0.1"
