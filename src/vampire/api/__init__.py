"""HTTP API layers exposed by the Vampire gateway.

The package is split along the DESIGN-API.md layering:

* :mod:`vampire.api.openai_compat` owns the compatibility-first ``/v1/*``
  surface that existing OpenAI-compatible clients can use unchanged.
* :mod:`vampire.api.control` owns the opt-in ``/vampire/v1/*`` control surface
  for cluster status and owner-approved node management.
"""
