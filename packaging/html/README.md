# HTML helper apps

Each file in this directory is a **self-contained single-file
HTML/JS/CSS application** — all markup, styles, and scripts are inlined, so the
files run directly in a browser with no build step or bundler.

LLM Vampire is the product; these are supporting browser tools that talk to
local LLM surfaces directly from the browser.

| File | Purpose |
| --- | --- |
| [`landing.html`](landing.html) | Marketing/landing page describing the gateway. |
| [`vampire-scanner.html`](vampire-scanner.html) | Browser scanner that probes local LLM surfaces and identity headers. |

## Building / packaging

Because these are already standalone apps, "building" just stages them for
distribution. Run from the repository root:

```bash
scripts/packaging/build-html-apps.sh
```

This copies every `*.html` app in this folder into `dist/html/`.
