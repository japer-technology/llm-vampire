# 08 — Headless Operation: llmster and Headless Desktop Mode

LM Studio can run as a background service without a GUI — turning servers, GPU rigs,
and always-on machines into Vampire-eligible nodes.

## Option 1: llmster (recommended)

**llmster** is the core of the LM Studio desktop app packaged as a standalone,
server-native daemon (LM Studio 0.4.0+). It runs on Linux boxes, cloud servers, GPU
rigs, or local machines with no GUI dependency.

### Install

```bash
# Linux / Mac
curl -fsSL https://lmstudio.ai/install.sh | bash
```

```powershell
# Windows
irm https://lmstudio.ai/install.ps1 | iex
```

### Operate

```bash
lms daemon up        # start the daemon
lms daemon status    # check status
lms daemon down      # stop the daemon
lms daemon update    # update llmster
```

llmster can be configured as a startup task (e.g. systemd on Linux) so the node
survives reboots.

## Option 2: Desktop app in headless mode

For machines that already run the GUI app:

- App settings → enable **"Run the LLM server on login"**.
- Exiting the app then minimizes it to the system tray; the LLM server keeps running.
- The last server state (on/off, port, settings) is saved and restored on launch;
  `lms server start` achieves the same programmatically.

## JIT loading completes the picture

Headless operation pairs with JIT model loading
([07-model-lifecycle.md](07-model-lifecycle.md)): the service starts with no models in
memory and loads them on demand when requests arrive, with TTL-based auto-unload
reclaiming memory afterwards. This is LM Studio's intended pattern for serving other
frontends and applications — which is precisely what Vampire is.

## Headless + LM Link

A headless machine can join an LM Link network entirely from the terminal
(`lms login`, then `lms link enable`) — see [09-lm-link.md](09-lm-link.md).

## Implications for Vampire

1. **Three node archetypes** behave identically over HTTP: GUI app with server on,
   GUI app headless/tray, and llmster daemon. Vampire needs no special-casing — but
   daemon nodes are the most reliable (always-on, restart-on-boot).
2. **Daemon nodes suit `trusted`/pinned roles** in Vampire's trust model
   ([`../DESIGN-API.md`](../DESIGN-API.md) §21): they are deliberately provisioned,
   not casually running desktops.
3. **Provisioning guidance.** Vampire's operator docs can give owners a one-liner
   recipe: install llmster → `lms daemon up` → `lms server start --bind 0.0.0.0` →
   enable authentication → register the endpoint with Vampire.
