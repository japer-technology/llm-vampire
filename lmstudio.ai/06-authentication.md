# 06 — Authentication: API Tokens

##### Requires LM Studio 0.4.0 or newer.

LM Studio supports API tokens for authenticating requests to the API server. This is
the mechanism behind Vampire's "respects owner tokens" commitment.

## How it works

- **Off by default.** A fresh LM Studio server accepts unauthenticated requests.
- The owner enables **Require Authentication** in Developer page → Server Settings.
  Once enabled, **all** requests — REST API, OpenAI-compatible endpoints, Python SDK,
  TypeScript SDK — must include a valid API token.
- Requests carry the token in the standard header:

  ```text
  Authorization: Bearer $LM_API_TOKEN
  ```

## Token management

- Tokens are created in **Manage Tokens** (Server Settings). Each token has a **name**
  and a set of **permissions** selected at creation time.
- A token's value is shown **once** at creation and cannot be retrieved later.
- Tokens can be edited (name, permissions) and deleted at any time by the owner.
- Multiple tokens can coexist — e.g. one per user, per app, or per Vampire instance.

## Example authenticated request

```bash
curl -X POST \
  http://localhost:1234/api/v1/chat \
  -H "Authorization: Bearer $LM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ibm/granite-4-micro",
    "input": "Hello!",
    "context_length": 8000
  }'
```

## Interactions with other settings

- **Serve on Local Network** and **CORS**: LM Studio recommends enabling
  authentication whenever the server is exposed beyond `127.0.0.1`.
- **Allow calling servers from mcp.json** *requires* authentication to be enabled —
  owner-defined MCP servers are only reachable by token-bearing clients.

## Implications for Vampire

1. **Token vault.** Vampire stores one token per node (provided by the node's owner at
   registration) and forwards it only to that node. Client-facing auth (Vampire's own
   tokens/realms) is a separate layer — node tokens are never exposed to clients.
2. **Scoped permissions.** Because owners choose per-token permissions, a node owner
   can hand Vampire a token that allows inference but not model loading, or vice
   versa. Vampire must discover effective permissions empirically (4xx responses) and
   degrade gracefully.
3. **Mixed fleets.** Some nodes require tokens and some do not; node records need an
   optional credential, not a mandatory one.
4. **Revocation is instant.** The owner deleting a token is equivalent to
   de-registering Vampire from that node; treat persistent 401/403 as "node withdrew
   consent" and remove it from rotation.
