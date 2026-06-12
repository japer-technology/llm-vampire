# 09 — LM Link: Remote-Device Model Routing

LM Link is LM Studio's own mechanism for using models on remote devices **as if they
were local**. It is the "LM Studio's own remote-device routing" referenced in
Vampire's README — and it means the compute behind an endpoint Vampire connects to may
physically live on a different machine.

## What it is

- Custom, **end-to-end-encrypted** device networks for loading and serving LLMs across
  devices you own, built in partnership with **Tailscale**.
- A link is **automatically provisioned** on first use; login associates devices with
  a user to facilitate discovery.
- The LM Studio Hub is used **only for discovery** between LM Studio/llmster
  instances. All subsequent communication — chats, model listing — flows inside
  Tailscale's end-to-end-encrypted tunnels. No device is exposed to the public
  internet.
- LM Link creates its own dedicated Tailscale network with fully controlled ACLs; it
  coexists with, but is separate from, any existing Tailscale VPN.
- Linked devices can only reach each other's LM Studio/llmster — not the OS, files,
  or other services.

## Adding devices

- **GUI machines:** install LM Studio → LM Link sidebar icon → enable. Devices connect
  automatically.
- **Headless machines:** install llmster, then:

  ```bash
  lms login        # associate the machine with your account
  lms link enable  # join the link
  ```

## How remote models behave

- The model loader shows **local and remote models together**; remote models load and
  configure with the same controls (GUI or `lms`).
- The same model on multiple devices appears as **separate entries**, tagged with the
  device name.
- A per-machine **preferred device** setting (`lms link set-preferred-device`)
  determines which device serves a model that exists on several.
- **The local server transparently uses remote models.** Any tool pointing at
  `localhost:1234` can use models physically loaded on a remote linked device; the
  REST API and SDKs work unchanged. For models on multiple devices, the API uses the
  preferred device.
- Parallel requests work across the link, serving multiple clients simultaneously.

## CLI reference

```bash
lms link enable               # join / enable LM Link
lms link disable              # leave / disable LM Link
lms link status               # show link status
lms link set-device-name      # rename this device on the link
lms link set-preferred-device # choose which device serves shared models
```

## Implications for Vampire

1. **A "node" is an endpoint, not a machine.** One LM Studio endpoint may front an
   entire LM Link network; the model that answers may run elsewhere. Vampire's design
   principle — "Vampire does not need to know where the GPU is" — exists because of
   this mechanism.
2. **Latency attribution.** TPS/TTFT observed at an endpoint includes any LM Link hop
   behind it. Metrics belong to the endpoint, not to assumed hardware.
3. **Complement, not competitor.** LM Link federates devices *one owner* trusts under
   *one account*; Vampire federates endpoints across *multiple owners* with
   governance, policy, and aggregation. A family might use LM Link inside the house
   and register the resulting single endpoint with a community Vampire.
4. **Inventory may shift invisibly.** Models can appear/disappear at an endpoint as
   remote devices join or leave its link — another reason interrogation must be
   periodic, and `/v1/models` results treated as snapshots.
