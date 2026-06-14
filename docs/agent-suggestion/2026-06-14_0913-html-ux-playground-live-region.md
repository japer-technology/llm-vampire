# Prompt playground output is not announced to assistive tech

- **Severity:** Medium
- **Category:** ux (accessibility)
- **Summary:** In the dashboard SPA the prompt-playground result panel (`#playground-output`) is updated asynchronously after a `/v1/chat/completions` round-trip, but it carries no ARIA live-region semantics. Screen-reader users get no feedback when a response arrives or when the request errors — the text silently changes off-screen.

## Location
`web/index.html:268` — the `<pre id="playground-output">` element, populated by the `prompt-form` submit handler at `web/index.html:651-659` (`Waiting…`, JSON response, or `error.message`).

## Evidence
Before:
```html
<pre id="playground-output">Responses from /v1/chat/completions appear here.</pre>
```
The submit handler swaps `.textContent` to "Waiting for /v1/chat/completions…", then to the JSON response or the error message. None of these transitions are announced because the region is a plain `<pre>` with no `role`/`aria-live`.

After:
```html
<pre id="playground-output" role="status" aria-live="polite" aria-atomic="true" aria-label="Prompt playground response">Responses from /v1/chat/completions appear here.</pre>
```

## Impact
Keyboard/screen-reader users submitting a prompt receive no confirmation that the gateway responded or failed — a WCAG 2.1 4.1.3 (Status Messages) gap. `aria-atomic="true"` ensures the whole panel (not just a diffed fragment) is read on each update; `aria-live="polite"` avoids interrupting the user mid-action.

## Fix
Add `role="status"`, `aria-live="polite"`, `aria-atomic="true"`, and an `aria-label` to the output `<pre>`. Pure markup change; no JS or styling touched, existing visual behavior preserved.

## Effort
Trivial (1 line).

> APPLIED 2026-06-14T09:13:57Z on branch vampire-fix/html-ux-playground-live-region: html parses, tests green (93 passed; only the documented LM-Studio-live flake `test_openai_route_proxies_upstream_error_when_node_unreachable` failed, 200 vs 502). Awaiting review.
